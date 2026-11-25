// SPDX-License-Identifier: MIT
#include <vulkan/vulkan.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using std::uint32_t;
using std::uint64_t;

static constexpr uint32_t ring_size = 3;
static constexpr uint32_t threads_per_group = 256;
static constexpr uint64_t wait_timeout_ns = 30'000'000'000;
static constexpr VkMemoryPropertyFlags staging_flags = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT;

static void require(bool valid, const char *message)
{
    if (!valid) throw std::runtime_error(message);
}

static void check(VkResult result, const char *call)
{
    if (result != VK_SUCCESS) {
        throw std::runtime_error(std::string(call) + ": " + std::to_string(result));
    }
}

template <typename T>
static T vk_structure(VkStructureType type)
{
    T result{};
    result.sType = type;
    return result;
}

struct Range {
    uint32_t first_page;
    uint32_t page_count;
};

struct Frame {
    uint32_t epoch;
    uint64_t expected_hash;
    std::vector<Range> writes;
    std::vector<Range> observes;
    std::vector<Range> deltas;
};

struct Trace {
    uint32_t page_bytes;
    uint32_t total_pages;
    std::vector<Frame> frames;

    uint32_t page_words() const { return page_bytes / sizeof(uint32_t); }
    VkDeviceSize bytes() const { return VkDeviceSize(page_bytes) * total_pages; }
};

static std::vector<Range> read_ranges(std::istream &input, uint32_t count, uint32_t total_pages)
{
    require(count <= total_pages, "range count exceeds source size");
    std::vector<Range> ranges;
    ranges.reserve(count);
    uint32_t previous_end = 0;
    for (uint32_t i = 0; i < count; ++i) {
        Range range{};
        require(bool(input >> range.first_page >> range.page_count), "cannot read a trace range");
        require(range.first_page < total_pages && range.page_count > 0 &&
                range.page_count <= total_pages - range.first_page, "trace range is out of bounds");
        require(i == 0 || range.first_page > previous_end, "trace ranges must be sorted and merged");
        previous_end = range.first_page + range.page_count;
        ranges.push_back(range);
    }
    return ranges;
}

static Trace read_trace(const char *path)
{
    std::ifstream input(path);
    Trace trace{};
    uint32_t frame_count = 0;
    require(bool(input >> trace.page_bytes >> trace.total_pages >> frame_count), "cannot read trace header");
    require(trace.page_bytes != 0 && trace.page_bytes % sizeof(uint32_t) == 0 &&
            trace.total_pages != 0 && trace.bytes() / sizeof(uint32_t) <= std::numeric_limits<uint32_t>::max(),
            "invalid trace dimensions");
    require(frame_count > 0 && frame_count <= 1'000'000, "invalid frame count");
    trace.frames.reserve(frame_count);
    for (uint32_t i = 0; i < frame_count; ++i) {
        Frame frame{};
        uint32_t writes = 0, observes = 0, deltas = 0;
        require(bool(input >> frame.epoch >> writes >> observes >> deltas >> frame.expected_hash),
                "cannot read a trace frame");
        frame.writes = read_ranges(input, writes, trace.total_pages);
        frame.observes = read_ranges(input, observes, trace.total_pages);
        frame.deltas = read_ranges(input, deltas, trace.total_pages);
        trace.frames.push_back(std::move(frame));
    }
    std::string extra;
    require(!(input >> extra) && input.eof(), "unexpected trailing trace input");
    return trace;
}

struct Buffer {
    VkBuffer handle{};
    VkDeviceMemory memory{};
    VkDeviceSize allocation_bytes{};
};

struct Slot {
    Buffer staging;
    uint32_t *mapped{};
    VkCommandBuffer command{};
    VkFence fence{};
};

struct PushConstants {
    uint32_t first_word;
    uint32_t word_count;
    uint32_t epoch;
};

struct Replay {
    VkInstance instance{};
    VkPhysicalDevice physical{};
    VkPhysicalDeviceProperties properties{};
    VkPhysicalDeviceMemoryProperties memory_properties{};
    VkDevice device{};
    VkQueue queue{};
    VkCommandPool pool{};
    Buffer source;
    VkDescriptorSetLayout descriptor_layout{};
    VkDescriptorPool descriptor_pool{};
    VkDescriptorSet descriptor{};
    VkPipelineLayout pipeline_layout{};
    VkPipeline pipeline{};
    std::array<Slot, ring_size> slots{};

    ~Replay()
    {
        if (device) {
            vkDeviceWaitIdle(device);
            for (const auto &slot : slots) {
                if (slot.mapped) vkUnmapMemory(device, slot.staging.memory);
                vkDestroyFence(device, slot.fence, nullptr);
                vkDestroyBuffer(device, slot.staging.handle, nullptr);
                vkFreeMemory(device, slot.staging.memory, nullptr);
            }
            vkDestroyPipeline(device, pipeline, nullptr);
            vkDestroyPipelineLayout(device, pipeline_layout, nullptr);
            vkDestroyDescriptorPool(device, descriptor_pool, nullptr);
            vkDestroyDescriptorSetLayout(device, descriptor_layout, nullptr);
            vkDestroyBuffer(device, source.handle, nullptr);
            vkFreeMemory(device, source.memory, nullptr);
            vkDestroyCommandPool(device, pool, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        if (instance) vkDestroyInstance(instance, nullptr);
    }

    void create_buffer(Buffer &buffer, VkDeviceSize bytes, VkBufferUsageFlags usage,
                       VkMemoryPropertyFlags required, VkMemoryPropertyFlags avoid)
    {
        auto info = vk_structure<VkBufferCreateInfo>(VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO);
        info.size = bytes;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(vkCreateBuffer(device, &info, nullptr, &buffer.handle), "vkCreateBuffer");

        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(device, buffer.handle, &requirements);
        uint32_t memory_type = memory_properties.memoryTypeCount;
        for (uint32_t i = 0; i < memory_properties.memoryTypeCount; ++i) {
            const auto flags = memory_properties.memoryTypes[i].propertyFlags;
            if (!(requirements.memoryTypeBits & (1u << i)) || (flags & required) != required) continue;
            if (memory_type == memory_properties.memoryTypeCount || !(flags & avoid)) memory_type = i;
            if (!(flags & avoid)) break;
        }
        require(memory_type < memory_properties.memoryTypeCount, "required Vulkan memory type unavailable");
        auto allocation = vk_structure<VkMemoryAllocateInfo>(VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO);
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memory_type;
        buffer.allocation_bytes = requirements.size;
        check(vkAllocateMemory(device, &allocation, nullptr, &buffer.memory), "vkAllocateMemory");
        check(vkBindBufferMemory(device, buffer.handle, buffer.memory, 0), "vkBindBufferMemory");
    }

    void create_pipeline(const char *spirv_path, VkDeviceSize bytes)
    {
        VkDescriptorSetLayoutBinding binding{};
        binding.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        binding.descriptorCount = 1;
        binding.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
        auto descriptor_info = vk_structure<VkDescriptorSetLayoutCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO);
        descriptor_info.bindingCount = 1;
        descriptor_info.pBindings = &binding;
        check(vkCreateDescriptorSetLayout(device, &descriptor_info, nullptr, &descriptor_layout),
              "vkCreateDescriptorSetLayout");

        const VkDescriptorPoolSize size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1};
        auto pool_info = vk_structure<VkDescriptorPoolCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO);
        pool_info.maxSets = 1;
        pool_info.poolSizeCount = 1;
        pool_info.pPoolSizes = &size;
        check(vkCreateDescriptorPool(device, &pool_info, nullptr, &descriptor_pool), "vkCreateDescriptorPool");

        auto allocation = vk_structure<VkDescriptorSetAllocateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO);
        allocation.descriptorPool = descriptor_pool;
        allocation.descriptorSetCount = 1;
        allocation.pSetLayouts = &descriptor_layout;
        check(vkAllocateDescriptorSets(device, &allocation, &descriptor), "vkAllocateDescriptorSets");

        const VkDescriptorBufferInfo source_info{source.handle, 0, bytes};
        auto write = vk_structure<VkWriteDescriptorSet>(VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET);
        write.dstSet = descriptor;
        write.descriptorCount = 1;
        write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        write.pBufferInfo = &source_info;
        vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);

        const VkPushConstantRange push{VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(PushConstants)};
        auto layout_info = vk_structure<VkPipelineLayoutCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO);
        layout_info.setLayoutCount = 1;
        layout_info.pSetLayouts = &descriptor_layout;
        layout_info.pushConstantRangeCount = 1;
        layout_info.pPushConstantRanges = &push;
        check(vkCreatePipelineLayout(device, &layout_info, nullptr, &pipeline_layout), "vkCreatePipelineLayout");

        std::ifstream file(spirv_path, std::ios::ate | std::ios::binary);
        const std::streamoff size_bytes = file.tellg();
        require(size_bytes >= 20 && size_bytes % 4 == 0, "invalid SPIR-V length");
        std::vector<uint32_t> words(static_cast<size_t>(size_bytes / sizeof(uint32_t)));
        file.seekg(0);
        require(bool(file.read(reinterpret_cast<char *>(words.data()), size_bytes)) && words[0] == 0x07230203u,
                "cannot read a valid SPIR-V module");
        auto shader_info = vk_structure<VkShaderModuleCreateInfo>(VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO);
        shader_info.codeSize = static_cast<size_t>(size_bytes);
        shader_info.pCode = words.data();
        VkShaderModule shader{};
        check(vkCreateShaderModule(device, &shader_info, nullptr, &shader), "vkCreateShaderModule");

        auto info = vk_structure<VkComputePipelineCreateInfo>(VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO);
        info.stage = vk_structure<VkPipelineShaderStageCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO);
        info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        info.stage.module = shader;
        info.stage.pName = "main";
        info.layout = pipeline_layout;
        VkResult result = vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &info, nullptr, &pipeline);
        vkDestroyShaderModule(device, shader, nullptr);
        check(result, "vkCreateComputePipelines");
    }

    void initialize(const char *spirv_path, VkDeviceSize bytes,
                    const std::array<VkDeviceSize, ring_size> &staging_bytes, std::string_view selector)
    {
        auto application = vk_structure<VkApplicationInfo>(VK_STRUCTURE_TYPE_APPLICATION_INFO);
        application.pApplicationName = "PortBridge Readback Replay";
        application.apiVersion = VK_API_VERSION_1_1;
        auto instance_info = vk_structure<VkInstanceCreateInfo>(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO);
        instance_info.pApplicationInfo = &application;
        check(vkCreateInstance(&instance_info, nullptr, &instance), "vkCreateInstance");

        uint32_t count{};
        check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "vkEnumeratePhysicalDevices");
        std::vector<VkPhysicalDevice> devices(count);
        check(vkEnumeratePhysicalDevices(instance, &count, devices.data()), "vkEnumeratePhysicalDevices");
        for (const auto candidate : devices) {
            VkPhysicalDeviceProperties candidate_properties{};
            vkGetPhysicalDeviceProperties(candidate, &candidate_properties);
            if (std::string_view(candidate_properties.deviceName).find(selector) == std::string_view::npos) continue;
            require(!physical, "more than one Vulkan device matches the selector");
            physical = candidate;
            properties = candidate_properties;
        }
        require(physical != VK_NULL_HANDLE, "no Vulkan device matches the selector");
        require(bytes <= properties.limits.maxStorageBufferRange &&
                properties.limits.maxComputeWorkGroupInvocations >= threads_per_group &&
                properties.limits.maxComputeWorkGroupSize[0] >= threads_per_group,
                "trace is unsupported by Vulkan device limits");
        vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);

        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
        const auto family = std::find_if(families.begin(), families.end(), [](const auto &item) {
            return item.queueCount != 0 && (item.queueFlags & VK_QUEUE_COMPUTE_BIT);
        });
        require(family != families.end(), "no compute queue");
        const auto queue_index = static_cast<uint32_t>(family - families.begin());
        float priority = 1.0f;
        auto queue_info = vk_structure<VkDeviceQueueCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO);
        queue_info.queueFamilyIndex = queue_index;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        auto device_info = vk_structure<VkDeviceCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO);
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        check(vkCreateDevice(physical, &device_info, nullptr, &device), "vkCreateDevice");
        vkGetDeviceQueue(device, queue_index, 0, &queue);

        auto pool_info = vk_structure<VkCommandPoolCreateInfo>(VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO);
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = queue_index;
        check(vkCreateCommandPool(device, &pool_info, nullptr, &pool), "vkCreateCommandPool");
        auto allocation = vk_structure<VkCommandBufferAllocateInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO);
        allocation.commandPool = pool;
        allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocation.commandBufferCount = ring_size;
        std::array<VkCommandBuffer, ring_size> commands{};
        check(vkAllocateCommandBuffers(device, &allocation, commands.data()), "vkAllocateCommandBuffers");

        create_buffer(source, bytes, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
                      VK_BUFFER_USAGE_TRANSFER_DST_BIT, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
        for (uint32_t i = 0; i < ring_size; ++i) {
            auto &slot = slots[i];
            slot.command = commands[i];
            create_buffer(slot.staging, staging_bytes[i], VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                          staging_flags, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
            void *mapped{};
            check(vkMapMemory(device, slot.staging.memory, 0, VK_WHOLE_SIZE, 0, &mapped), "vkMapMemory");
            slot.mapped = static_cast<uint32_t *>(mapped);
            const auto fence_info = vk_structure<VkFenceCreateInfo>(VK_STRUCTURE_TYPE_FENCE_CREATE_INFO);
            check(vkCreateFence(device, &fence_info, nullptr, &slot.fence), "vkCreateFence");
        }
        create_pipeline(spirv_path, bytes);
    }

    void begin(const Slot &slot) const
    {
        check(vkResetFences(device, 1, &slot.fence), "vkResetFences");
        check(vkResetCommandBuffer(slot.command, 0), "vkResetCommandBuffer");
        auto info = vk_structure<VkCommandBufferBeginInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO);
        info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(slot.command, &info), "vkBeginCommandBuffer");
    }

    void submit(const Slot &slot) const
    {
        check(vkEndCommandBuffer(slot.command), "vkEndCommandBuffer");
        auto info = vk_structure<VkSubmitInfo>(VK_STRUCTURE_TYPE_SUBMIT_INFO);
        info.commandBufferCount = 1;
        info.pCommandBuffers = &slot.command;
        check(vkQueueSubmit(queue, 1, &info, slot.fence), "vkQueueSubmit");
    }

    void wait(const Slot &slot) const
    {
        check(vkWaitForFences(device, 1, &slot.fence, VK_TRUE, wait_timeout_ns), "vkWaitForFences");
    }
};

static void barrier(VkCommandBuffer command, VkBuffer buffer, VkPipelineStageFlags from,
                    VkPipelineStageFlags to, VkAccessFlags source, VkAccessFlags destination)
{
    auto info = vk_structure<VkBufferMemoryBarrier>(VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER);
    info.srcAccessMask = source;
    info.dstAccessMask = destination;
    info.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    info.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    info.buffer = buffer;
    info.size = VK_WHOLE_SIZE;
    vkCmdPipelineBarrier(command, from, to, 0, 0, nullptr, 1, &info, 0, nullptr);
}

enum class Mode { full, ranges, epochs };

static std::span<const Range> copies_for(const Frame &frame, Mode mode, const Range &full)
{
    switch (mode) {
    case Mode::full: return {&full, 1};
    case Mode::ranges: return frame.observes;
    case Mode::epochs: return frame.deltas;
    }
    throw std::runtime_error("unknown replay mode");
}

static std::string_view effective_name(Mode mode)
{
    switch (mode) {
    case Mode::full: return "full";
    case Mode::ranges: return "ranges";
    case Mode::epochs: return "epochs";
    }
    throw std::runtime_error("unknown replay mode");
}

static VkDeviceSize packed_bytes(std::span<const Range> ranges, uint32_t page_bytes)
{
    VkDeviceSize bytes = 0;
    for (const auto &range : ranges) bytes += VkDeviceSize(range.page_count) * page_bytes;
    return bytes;
}

static Mode select_mode(std::string_view requested, const Trace &trace)
{
    if (requested == "full") return Mode::full;
    if (requested == "ranges") return Mode::ranges;
    if (requested == "epochs") return Mode::epochs;
    require(requested == "guarded", "use mode full, ranges, epochs or guarded");

    VkDeviceSize full_reads = 0, delta_reads = 0;
    for (const auto &frame : trace.frames) {
        full_reads += packed_bytes(frame.observes, trace.page_bytes);
        delta_reads += packed_bytes(frame.deltas, trace.page_bytes);
    }
    if (delta_reads <= full_reads / 2 && full_reads - delta_reads >= 1024 * 1024) return Mode::epochs;
    return Mode::ranges;
}

struct MirrorWindow {
    Range canonical;
    size_t dense_first_page;
};

struct PackedLayout {
    std::array<VkDeviceSize, ring_size> staging_bytes{};
    std::vector<MirrorWindow> mirror_windows;
    size_t mirror_pages{};

    size_t mirror_page(Range range) const
    {
        const auto next = std::upper_bound(mirror_windows.begin(), mirror_windows.end(), range.first_page,
            [](uint32_t first, const MirrorWindow &entry) { return first < entry.canonical.first_page; });
        require(next != mirror_windows.begin(), "range starts outside the observed mirror");
        const auto &entry = *(next - 1);
        const uint32_t relative = range.first_page - entry.canonical.first_page;
        require(relative < entry.canonical.page_count &&
                range.page_count <= entry.canonical.page_count - relative,
                "range crosses an unobserved mirror gap");
        return entry.dense_first_page + relative;
    }
};

static PackedLayout pack_layout(const Trace &trace, Mode mode)
{
    PackedLayout layout;
    layout.staging_bytes.fill(trace.page_bytes);
    const Range full{0, trace.total_pages};
    std::vector<Range> windows;
    for (size_t index = 0; index < trace.frames.size(); ++index) {
        const auto &frame = trace.frames[index];
        auto &capacity = layout.staging_bytes[index % ring_size];
        capacity = std::max(capacity, packed_bytes(copies_for(frame, mode, full), trace.page_bytes));
        if (mode == Mode::epochs) windows.insert(windows.end(), frame.observes.begin(), frame.observes.end());
    }
    std::sort(windows.begin(), windows.end(),
              [](Range left, Range right) { return left.first_page < right.first_page; });
    for (const Range range : windows) {
        const uint32_t end = range.first_page + range.page_count;
        if (!layout.mirror_windows.empty()) {
            auto &last = layout.mirror_windows.back().canonical;
            const uint32_t last_end = last.first_page + last.page_count;
            if (range.first_page <= last_end) {
                if (end > last_end) {
                    layout.mirror_pages += end - last_end;
                    last.page_count = end - last.first_page;
                }
                continue;
            }
        }
        layout.mirror_windows.push_back({range, layout.mirror_pages});
        layout.mirror_pages += range.page_count;
    }
    if (mode == Mode::epochs) {
        for (const auto &frame : trace.frames)
            for (const auto &range : frame.deltas) layout.mirror_page(range);
    }
    return layout;
}

static uint64_t record_frame(const Replay &replay, const Slot &slot, const Frame &frame,
                             std::span<const Range> planned, const Trace &trace,
                             std::vector<VkBufferCopy> &copies)
{
    replay.begin(slot);
    const auto command = slot.command;
    const auto shader_or_transfer = VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | VK_PIPELINE_STAGE_TRANSFER_BIT;
    if (!frame.writes.empty()) {
        // A later dispatch must not overwrite a source range while a prior copy reads it.
        barrier(command, replay.source.handle, shader_or_transfer, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT | VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_ACCESS_SHADER_WRITE_BIT);
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_COMPUTE, replay.pipeline);
        vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_COMPUTE, replay.pipeline_layout, 0,
                               1, &replay.descriptor, 0, nullptr);
        const uint64_t dispatch_words =
            uint64_t(replay.properties.limits.maxComputeWorkGroupCount[0]) * threads_per_group;
        for (const auto &write : frame.writes) {
            uint32_t first_word = write.first_page * trace.page_words();
            uint32_t remaining = write.page_count * trace.page_words();
            while (remaining) {
                const auto batch = static_cast<uint32_t>(std::min<uint64_t>(remaining, dispatch_words));
                const auto groups = static_cast<uint32_t>((uint64_t(batch) + threads_per_group - 1) / threads_per_group);
                const PushConstants push{first_word, batch, frame.epoch};
                vkCmdPushConstants(command, replay.pipeline_layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(push), &push);
                vkCmdDispatch(command, groups, 1, 1);
                first_word += batch;
                remaining -= batch;
            }
        }
    }

    uint64_t copied_bytes = 0;
    if (!planned.empty()) {
        copies.clear();
        for (const auto &range : planned) {
            const auto offset = uint64_t(range.first_page) * trace.page_bytes;
            const auto bytes = uint64_t(range.page_count) * trace.page_bytes;
            copies.push_back({offset, copied_bytes, bytes});
            copied_bytes += bytes;
        }
        barrier(command, replay.source.handle, shader_or_transfer, VK_PIPELINE_STAGE_TRANSFER_BIT,
                VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        vkCmdCopyBuffer(command, replay.source.handle, slot.staging.handle,
                        static_cast<uint32_t>(copies.size()), copies.data());
        barrier(command, slot.staging.handle, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
    }
    replay.submit(slot);
    return copied_bytes;
}

static uint64_t observed_hash(const uint32_t *memory, const Frame &frame, size_t page_words,
                              Mode mode, const PackedLayout &layout)
{
    uint64_t hash = 1469598103934665603ull;
    size_t packed_first = 0;
    for (const auto &range : frame.observes) {
        size_t first = range.first_page;
        if (mode == Mode::ranges) first = packed_first;
        if (mode == Mode::epochs) first = layout.mirror_page(range);
        for (size_t page = first; page < first + range.page_count; ++page) {
            const auto *words = memory + page * page_words;
            for (const uint32_t word : {words[0], words[page_words / 2], words[page_words - 1]}) {
                hash = (hash ^ word) * 1099511628211ull;
            }
        }
        packed_first += range.page_count;
    }
    return hash;
}

struct Result {
    double wall_us;
    uint64_t copied_bytes;
    uint64_t observed_pages;
};

static Result trial(const Replay &replay, const Trace &trace, Mode mode, const PackedLayout &layout)
{
    const auto &initial = replay.slots[0];
    replay.begin(initial);
    vkCmdFillBuffer(initial.command, replay.source.handle, 0, VK_WHOLE_SIZE, 0);
    replay.submit(initial);
    replay.wait(initial);

    std::vector<uint32_t> mirror(layout.mirror_pages * trace.page_words());
    const Range full{0, trace.total_pages};
    std::vector<VkBufferCopy> copies;
    size_t maximum_copies = 1;
    for (const auto &frame : trace.frames) {
        maximum_copies = std::max(maximum_copies, copies_for(frame, mode, full).size());
    }
    copies.reserve(maximum_copies);
    uint64_t observed_pages = 0;
    const auto drain = [&](size_t index) {
        const auto &slot = replay.slots[index % ring_size];
        const auto &frame = trace.frames[index];
        replay.wait(slot);
        const uint32_t *memory = slot.mapped;
        if (mode == Mode::epochs) {
            size_t packed_first = 0;
            for (const auto &range : frame.deltas) {
                const size_t first = layout.mirror_page(range);
                const size_t bytes = size_t(range.page_count) * trace.page_bytes;
                std::memcpy(mirror.data() + first * trace.page_words(),
                            slot.mapped + packed_first * trace.page_words(), bytes);
                packed_first += range.page_count;
            }
            memory = mirror.data();
        }
        const auto hash = observed_hash(memory, frame, trace.page_words(), mode, layout);
        if (hash != frame.expected_hash) {
            throw std::runtime_error("frame " + std::to_string(index) + " expected hash " +
                                     std::to_string(frame.expected_hash) + " got " + std::to_string(hash));
        }
        for (const auto &range : frame.observes) observed_pages += range.page_count;
    };

    uint64_t copied_bytes = 0;
    const auto start = std::chrono::steady_clock::now();
    for (size_t index = 0; index < trace.frames.size(); ++index) {
        if (index >= ring_size) drain(index - ring_size);
        const auto &frame = trace.frames[index];
        copied_bytes += record_frame(replay, replay.slots[index % ring_size], frame,
                                     copies_for(frame, mode, full), trace, copies);
    }
    const size_t outstanding = std::min(trace.frames.size(), size_t(ring_size));
    for (size_t index = trace.frames.size() - outstanding; index < trace.frames.size(); ++index) drain(index);
    const auto elapsed = std::chrono::steady_clock::now() - start;
    return {std::chrono::duration<double, std::micro>(elapsed).count(), copied_bytes, observed_pages};
}

static std::string csv_string(std::string_view value)
{
    std::string escaped = "\"";
    for (char character : value) {
        if (character == '"') escaped += '"';
        escaped += character;
    }
    return escaped + '"';
}

int main(int argc, char **argv)
{
    if (argc != 6) {
        std::cerr << "usage: replay_vulkan producer.spv trace.tsv full|ranges|epochs|guarded repeats device_substring\n";
        return 2;
    }
    try {
        const auto trace = read_trace(argv[2]);
        const std::string_view requested(argv[3]);
        const Mode mode = select_mode(requested, trace);
        const auto layout = pack_layout(trace, mode);

        size_t consumed = 0;
        const std::string repeats_text(argv[4]);
        const auto repeats = std::stoul(repeats_text, &consumed);
        require(consumed == repeats_text.size() && repeats > 0 && repeats <= 256, "invalid repeat count");
        require(argv[5][0] != '\0', "an explicit Vulkan device selector is required");
        Replay replay;
        replay.initialize(argv[1], trace.bytes(), layout.staging_bytes, argv[5]);
        VkDeviceSize staging_allocation_bytes = 0;
        for (const auto &slot : replay.slots) staging_allocation_bytes += slot.staging.allocation_bytes;
        const VkDeviceSize mirror_bytes = VkDeviceSize(layout.mirror_pages) * trace.page_bytes;
        const auto version = replay.properties.apiVersion;
        std::cerr << replay.properties.deviceName << " Vulkan " << VK_VERSION_MAJOR(version) << '.'
                  << VK_VERSION_MINOR(version) << '.' << VK_VERSION_PATCH(version) << " driver " << replay.properties.driverVersion
                  << " staging host-visible/coherent/cached ring=" << ring_size << '\n';
        trial(replay, trace, mode, layout);
        std::cout << "device,mode,repeat,wall_us,copied_bytes,observed_pages,frame_count,"
                     "staging_allocation_bytes,mirror_bytes,effective_mode\n" << std::fixed << std::setprecision(3);
        for (uint32_t repeat = 0; repeat < repeats; ++repeat) {
            const auto result = trial(replay, trace, mode, layout);
            std::cout << csv_string(replay.properties.deviceName) << ',' << requested << ',' << repeat << ','
                      << result.wall_us << ',' << result.copied_bytes << ',' << result.observed_pages << ','
                      << trace.frames.size() << ',' << staging_allocation_bytes << ',' << mirror_bytes << ','
                      << effective_name(mode) << '\n';
        }
        return 0;
    }
    catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
