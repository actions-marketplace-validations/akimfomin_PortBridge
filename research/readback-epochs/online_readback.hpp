// SPDX-License-Identifier: MIT
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <vector>

namespace pb_readback {

struct Range {
    uint32_t first_page;
    uint32_t page_count;
    bool operator==(const Range&) const = default;
};

enum class Policy { retain, adaptive };
enum class Route { exact, seed, reuse };

struct Decision {
    Route route;
    bool rebind;
    std::vector<Range> copies;
    std::vector<std::size_t> mirror_pages;
};

// One ordered device queue and FIFO host retirement. A promised page is available
// to later plans, but its payload becomes readable only after its originating slot
// completes and is retired. A failed operation invalidates this planner instance.
class OnlinePlanner {
public:
    OnlinePlanner(uint32_t total_pages, uint32_t cache_pages, Policy policy, uint32_t minimum_saved_pages = 0)
        : total_pages_(total_pages), cache_pages_(cache_pages), policy_(policy),
          minimum_saved_pages_(minimum_saved_pages)
    {
        if (!total_pages) throw std::invalid_argument("empty readback backing");
    }

    Decision plan(std::span<const Range> writes, std::span<const Range> observes)
    {
        validate(writes);
        const auto requested = validate(observes);
        invalidate(writes);

        if (!requested || requested > cache_pages_ ||
            (policy_ == Policy::adaptive && requested < minimum_saved_pages_)) {
            previous_.clear();
            return exact(observes);
        }

        const bool repeated = same_shape(observes, previous_);
        if (!repeated) previous_.assign(observes.begin(), observes.end());
        const bool bound = same_shape(observes, shape_);
        if (policy_ == Policy::retain && !bound) return bind(observes, requested);

        CostShape written{};
        if (policy_ == Policy::adaptive) {
            written = overlap(observes, writes);
            if (written.pages * 2 > requested) return exact(observes);
            if (!bound) {
                if (requested - written.pages >= minimum_saved_pages_ &&
                    worth_seeding(repeated, written, requested, observes.size())) return bind(observes, requested);
                return exact(observes);
            }
        }

        auto delta = missing();
        if (policy_ == Policy::adaptive) {
            const auto missing_pages = count_pages(delta.copies);
            if (requested - missing_pages < minimum_saved_pages_ ||
                !worth_reuse(missing_pages, delta.copies.size(), requested, observes.size())) {
                if (requested - written.pages >= minimum_saved_pages_ &&
                    worth_seeding(repeated, written, requested, observes.size())) return seed();
                return exact(observes);
            }
        }

        for (std::size_t i = 0; i < delta.copies.size(); ++i) {
            std::fill_n(promised_.begin() + delta.mirror_pages[i], delta.copies[i].page_count, std::uint8_t{1});
        }
        return delta;
    }

private:
    const uint32_t total_pages_;
    const uint32_t cache_pages_;
    const Policy policy_;
    const uint32_t minimum_saved_pages_;
    std::vector<Range> previous_;
    std::vector<Range> shape_;
    std::vector<std::size_t> offsets_;
    std::vector<std::uint8_t> promised_;

    static std::uint64_t end(Range range)
    {
        return std::uint64_t(range.first_page) + range.page_count;
    }

    std::uint64_t validate(std::span<const Range> ranges) const
    {
        std::uint64_t previous_end = 0;
        std::uint64_t pages = 0;
        for (const auto range : ranges) {
            if (!range.page_count || end(range) > total_pages_ || range.first_page < previous_end)
                throw std::invalid_argument("unsorted, overlapping or invalid readback range");
            pages += range.page_count;
            previous_end = end(range);
        }
        return pages;
    }

    static bool same_shape(std::span<const Range> current, const std::vector<Range>& previous)
    {
        return std::equal(current.begin(), current.end(), previous.begin(), previous.end());
    }

    static std::uint64_t count_pages(std::span<const Range> ranges)
    {
        std::uint64_t pages = 0;
        for (const auto range : ranges) pages += range.page_count;
        return pages;
    }

    template<class Process>
    static void intersections(std::span<const Range> left, std::span<const Range> right, Process process)
    {
        std::size_t i = 0, j = 0;
        while (i < left.size() && j < right.size()) {
            const auto left_end = end(left[i]);
            const auto right_end = end(right[j]);
            const auto first = std::max(left[i].first_page, right[j].first_page);
            const auto last = std::min(left_end, right_end);
            if (first < last) process(i, first, last - first);
            if (left_end <= right_end) ++i;
            if (right_end <= left_end) ++j;
        }
    }

    struct CostShape {
        std::uint64_t pages = 0;
        std::size_t regions = 0;
    };

    static CostShape overlap(std::span<const Range> left, std::span<const Range> right)
    {
        CostShape written{};
        intersections(left, right, [&](auto, auto, auto count) {
            written.pages += count;
            ++written.regions;
        });
        return written;
    }

    void invalidate(std::span<const Range> writes)
    {
        intersections(shape_, writes, [&](std::size_t i, uint32_t first, std::uint64_t count) {
            const auto packed = offsets_[i] + (first - shape_[i].first_page);
            std::fill_n(promised_.begin() + packed, count, std::uint8_t{0});
        });
    }

    static Decision exact(std::span<const Range> observes)
    {
        return {Route::exact, false, {observes.begin(), observes.end()}, {}};
    }

    Decision bind(std::span<const Range> observes, std::uint64_t pages)
    {
        const bool rebind = !shape_.empty();
        shape_.assign(observes.begin(), observes.end());
        offsets_.clear();
        std::size_t offset = 0;
        for (const auto range : shape_) {
            offsets_.push_back(offset);
            offset += range.page_count;
        }
        promised_.assign(static_cast<std::size_t>(pages), 1);
        return {Route::seed, rebind, shape_, offsets_};
    }

    Decision seed()
    {
        std::fill(promised_.begin(), promised_.end(), std::uint8_t{1});
        return {Route::seed, false, shape_, offsets_};
    }

    Decision missing() const
    {
        Decision result{Route::reuse, false, {}, {}};
        for (std::size_t i = 0; i < shape_.size(); ++i) {
            const auto range = shape_[i];
            const auto offset = offsets_[i];
            uint32_t cursor = 0;
            while (cursor < range.page_count) {
                if (promised_[offset + cursor]) {
                    ++cursor;
                    continue;
                }
                const auto first = cursor;
                do {
                    ++cursor;
                } while (cursor < range.page_count && !promised_[offset + cursor]);
                result.copies.push_back({range.first_page + first, cursor - first});
                result.mirror_pages.push_back(offset + first);
            }
        }
        return result;
    }

    // Work units are deliberately conservative and independent of later requests.
    // Charge a region fee, a mirror-write premium, and a fixed planning margin.
    static bool worth_reuse(std::uint64_t pages, std::size_t regions,
                            std::uint64_t requested, std::size_t exact_regions)
    {
        const auto exact_cost = requested * 8 + exact_regions * std::uint64_t{24};
        const auto reuse_cost = pages * 9 + regions * std::uint64_t{24} + 32;
        return reuse_cost + exact_cost / 8 < exact_cost;
    }

    static bool worth_seeding(bool repeated, CostShape written,
                              std::uint64_t requested, std::size_t exact_regions)
    {
        return repeated && written.pages * 4 <= requested &&
               worth_reuse(written.pages, written.regions, requested, exact_regions);
    }
};

} // namespace pb_readback
