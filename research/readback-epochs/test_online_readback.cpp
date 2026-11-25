// SPDX-License-Identifier: MIT
#include "online_readback.hpp"

#include <cstdint>
#include <deque>
#include <initializer_list>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

using namespace pb_readback;

static void require(bool condition, const char* text)
{
    if (!condition) throw std::runtime_error(text);
}

static Decision plan(OnlinePlanner& planner,
                     std::initializer_list<Range> writes,
                     std::initializer_list<Range> observes)
{
    return planner.plan({writes.begin(), writes.size()}, {observes.begin(), observes.size()});
}

static std::vector<Range> ranges(std::initializer_list<Range> input)
{
    return input;
}

static void routes()
{
    OnlinePlanner retain{128, 64, Policy::retain};
    const auto initial = plan(retain, {}, {{4, 16}, {48, 24}});
    require(initial.route == Route::seed && !initial.rebind, "retain cold seed");
    require(initial.mirror_pages == std::vector<std::size_t>{0, 16}, "packed seed");
    const auto dirty = plan(retain, {{5, 2}, {58, 6}}, {{4, 16}, {48, 24}});
    require(dirty.route == Route::reuse && dirty.copies == ranges({{5, 2}, {58, 6}}), "clipped dirty");
    require(dirty.mirror_pages == std::vector<std::size_t>{1, 26}, "packed delta");
    const auto oversized = plan(retain, {{7, 1}}, {{16, 96}});
    require(oversized.route == Route::exact && oversized.mirror_pages.empty(), "budget fallback");
    const auto revisit = plan(retain, {}, {{4, 16}, {48, 24}});
    require(revisit.copies == ranges({{7, 1}}), "exact does not rearm stale mirror");
    const auto changed = plan(retain, {}, {{100, 20}});
    require(changed.route == Route::seed && changed.rebind, "armed shape change drains");

    OnlinePlanner adaptive{128, 64, Policy::adaptive};
    require(plan(adaptive, {}, {{0, 32}}).route == Route::exact, "adaptive cold copy");
    require(plan(adaptive, {}, {{0, 32}}).route == Route::seed, "adaptive repeated seed");
    const auto sparse = plan(adaptive, {{2, 1}}, {{0, 32}});
    require(sparse.route == Route::reuse && sparse.copies == ranges({{2, 1}}), "sparse reuse");
    const auto dense = plan(adaptive, {{0, 29}}, {{0, 32}});
    require(dense.route == Route::exact && dense.copies == ranges({{0, 32}}), "dense exact");
    const auto restarted = plan(adaptive, {}, {{0, 32}});
    require(restarted.route == Route::seed && !restarted.rebind, "reseed stale shape after quiet request");
    const auto reused = plan(adaptive, {}, {{0, 32}});
    require(reused.route == Route::reuse && reused.copies.empty(), "promised clean read");
    const auto fragmented = plan(adaptive, {{0, 1}, {2, 1}, {4, 1}, {6, 1},
                                              {8, 1}, {10, 1}, {12, 1}, {14, 1}}, {{0, 32}});
    require(fragmented.route == Route::exact, "few bytes but too many regions");
    require(plan(adaptive, {}, {{0, 32}}).route == Route::seed, "quiet fragmented shape can recover");
    require(plan(adaptive, {}, {{48, 20}}).route == Route::exact, "cold new shape exact");
    require(plan(adaptive, {{48, 20}}, {{48, 20}}).route == Route::exact, "full rewrite cannot seed");
    const auto adaptive_rebind = plan(adaptive, {}, {{48, 20}});
    require(adaptive_rebind.route == Route::seed && adaptive_rebind.rebind, "warm changed shape rebind");

    OnlinePlanner limited{4'194'304, 2, Policy::retain};
    const auto narrow = plan(limited, {{3'000'000, 300'000}}, {{4'194'300, 2}});
    require(narrow.route == Route::seed && narrow.mirror_pages == std::vector<std::size_t>{0},
            "small retained shape on wide backing");
    OnlinePlanner disabled{128, 0, Policy::retain};
    require(plan(disabled, {}, {{0, 1}}).route == Route::exact, "zero configured cache");
}

static void bounds()
{
    OnlinePlanner planner{128, 64, Policy::retain};
    plan(planner, {}, {{0, 32}});
    for (const auto& bad : {ranges({{0, 0}}), ranges({{127, 2}}),
                           ranges({{8, 2}, {9, 1}}), ranges({{8, 1}, {4, 1}})}) {
        bool threw = false;
        try {
            planner.plan(ranges({{0, 1}}), bad);
        } catch (const std::invalid_argument&) {
            threw = true;
        }
        require(threw, "malformed request rejected");
    }
    require(plan(planner, {}, {{0, 32}}).copies.empty(), "invalid request must not mutate promise");
}

static std::vector<uint64_t> gather(std::span<const uint64_t> source,
                                    std::span<const Range> selected)
{
    std::vector<uint64_t> result;
    for (const auto range : selected) {
        const auto first = source.begin() + range.first_page;
        result.insert(result.end(), first, first + range.page_count);
    }
    return result;
}

struct Slot {
    Decision decision;
    std::vector<uint64_t> captured;
    std::vector<uint64_t> expected;
};

static void fifo_oracle(Policy policy)
{
    constexpr uint32_t total = 128;
    OnlinePlanner planner{total, 48, policy};
    const std::vector<std::vector<Range>> shapes{
        {{0, 32}},
        {{0, 8}, {48, 8}, {72, 8}, {116, 8}},
        {{9, 21}, {80, 18}},
        {{16, 64}},
        {},
    };
    std::mt19937 rng{10942};
    std::vector<uint64_t> source(total);
    std::vector<uint64_t> mirror;
    std::deque<Slot> slots;
    const auto retire = [&] {
        auto slot = std::move(slots.front());
        slots.pop_front();
        if (slot.decision.route == Route::exact) {
            require(slot.captured == slot.expected, "exact capture mismatch");
            return;
        }
        std::size_t cursor = 0;
        for (std::size_t i = 0; i < slot.decision.copies.size(); ++i) {
            const auto count = slot.decision.copies[i].page_count;
            const auto offset = slot.decision.mirror_pages.at(i);
            require(offset + count <= mirror.size(), "old slot refers to wrong mirror");
            std::copy_n(slot.captured.begin() + cursor, count, mirror.begin() + offset);
            cursor += count;
        }
        require(mirror == slot.expected, "retired mirror mismatch");
    };

    std::size_t selected = 0;
    for (uint32_t epoch = 1; epoch < 4001; ++epoch) {
        if (rng() % 7 == 0) selected = rng() % shapes.size();
        const auto& observes = shapes[selected];
        const auto p = static_cast<uint32_t>(rng() % total);
        auto writes = ranges({{p, 1}});
        if (epoch % 11 == 0) writes = ranges({{0, total}});
        if (epoch % 13 == 0) writes.clear();
        for (const auto range : writes) {
            for (uint32_t i = range.first_page; i < range.first_page + range.page_count; ++i)
                source[i] = (uint64_t(epoch) << 32) | i;
        }
        const auto expected = gather(source, observes);
        auto decision = planner.plan(writes, observes);
        if (decision.rebind) {
            while (!slots.empty()) retire();
            mirror.clear();
        }
        if (decision.route == Route::seed && mirror.empty()) mirror.resize(expected.size());
        auto captured = gather(source, decision.copies);
        slots.push_back({std::move(decision), std::move(captured), expected});
        if (slots.size() == 3) retire();
    }
    while (!slots.empty()) retire();
}

static void prefixes()
{
    for (const auto policy : {Policy::retain, Policy::adaptive}) {
        const auto run = [policy](bool alternate_suffix) {
            OnlinePlanner planner{128, 32, policy};
            std::vector<Decision> prefix;
            for (uint32_t i = 0; i < 10; ++i)
                prefix.push_back(plan(planner, {{i % 4, 1}}, {{0, 24}}));
            if (alternate_suffix) plan(planner, {{0, 128}}, {{0, 128}});
            else plan(planner, {}, {{76, 32}});
            return prefix;
        };
        const auto left = run(false);
        const auto right = run(true);
        for (std::size_t i = 0; i < left.size(); ++i) {
            require(left[i].route == right[i].route && left[i].rebind == right[i].rebind &&
                    left[i].copies == right[i].copies && left[i].mirror_pages == right[i].mirror_pages,
                    "suffix influenced a prefix decision");
        }
    }
}

static void savings_floor()
{
    const std::vector<Range> empty;
    OnlinePlanner planner{128, 64, Policy::adaptive, 40};
    const std::vector<Range> small{{0, 32}};
    for (int i = 0; i < 4; ++i) {
        if (planner.plan(empty, small).route != Route::exact) {
            throw std::logic_error("small observations should not allocate a mirror");
        }
    }
    const std::vector<Range> large{{0, 60}};
    planner.plan(empty, large);
    if (planner.plan(empty, large).route != Route::seed ||
        planner.plan(empty, large).route != Route::reuse) {
        throw std::logic_error("minimum savings guard blocked a large stable observation");
    }
}

int main()
{
    try {
        routes();
        bounds();
        savings_floor();
        fifo_oracle(Policy::retain);
        fifo_oracle(Policy::adaptive);
        prefixes();
        std::cout << "Online readback planning: route, bounds, prefix, and 8,000 FIFO snapshot checks passed.\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
