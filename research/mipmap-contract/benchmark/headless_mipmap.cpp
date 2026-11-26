// SPDX-License-Identifier: MIT
#include <vulkan/vulkan.h>
#include "nvpro_pyramid/nvpro_pyramid_dispatch.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using std::uint32_t;
using std::uint64_t;
using Bytes = std::vector<unsigned char>;

static void require(bool condition, const char *operation)
{
    if (!condition) throw std::runtime_error(operation);
}

static void check(VkResult result, const char *operation)
{
    if (result != VK_SUCCESS) throw std::runtime_error(std::string(operation) + ": " + std::to_string(result));
}

static uint32_t memory_index(VkPhysicalDevice physical, uint32_t required, VkMemoryPropertyFlags flags)
{
    VkPhysicalDeviceMemoryProperties props{};
    vkGetPhysicalDeviceMemoryProperties(physical, &props);
    for (uint32_t i = 0; i < props.memoryTypeCount; ++i)
        if ((required & (1u << i)) && (props.memoryTypes[i].propertyFlags & flags) == flags) return i;
    throw std::runtime_error("no suitable Vulkan memory type");
}

static VkDeviceMemory bind_memory(VkPhysicalDevice physical, VkDevice device, VkMemoryRequirements req,
                                  VkMemoryPropertyFlags flags)
{
    VkMemoryAllocateInfo info{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    info.allocationSize = req.size;
    info.memoryTypeIndex = memory_index(physical, req.memoryTypeBits, flags);
    VkDeviceMemory memory{};
    check(vkAllocateMemory(device, &info, nullptr, &memory), "vkAllocateMemory");
    return memory;
}

static VkPipeline make_pipeline(VkDevice device, VkPipelineLayout layout, const std::filesystem::path &path,
                                bool fixed_full_wave32)
{
    std::ifstream file(path, std::ios::ate | std::ios::binary);
    const auto size = file.tellg();
    require(size > 0 && size % 4 == 0, "invalid SPIR-V module length");
    std::vector<uint32_t> code(static_cast<size_t>(size) / 4);
    file.seekg(0);
    require(bool(file.read(reinterpret_cast<char *>(code.data()), size)), "cannot read SPIR-V");
    VkShaderModuleCreateInfo shader_info{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    shader_info.codeSize = size;
    shader_info.pCode = code.data();
    VkShaderModule shader{};
    check(vkCreateShaderModule(device, &shader_info, nullptr, &shader), "vkCreateShaderModule");
    VkComputePipelineCreateInfo info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    info.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO};
    VkPipelineShaderStageRequiredSubgroupSizeCreateInfo required{
        VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_REQUIRED_SUBGROUP_SIZE_CREATE_INFO};
    if (fixed_full_wave32) {
        required.requiredSubgroupSize = 32;
        info.stage.pNext = &required;
        info.stage.flags = VK_PIPELINE_SHADER_STAGE_CREATE_REQUIRE_FULL_SUBGROUPS_BIT;
    }
    info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    info.stage.module = shader;
    info.stage.pName = "main";
    info.layout = layout;
    VkPipeline pipeline{};
    const VkResult result = vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &info, nullptr, &pipeline);
    vkDestroyShaderModule(device, shader, nullptr);
    check(result, "vkCreateComputePipelines");
    return pipeline;
}

static Bytes pixels(uint32_t width, uint32_t height, std::string_view pattern)
{
    if (pattern != "hashed" && pattern != "constant") {
        const auto size = size_t(width) * height * 4;
        std::ifstream input(std::filesystem::path(pattern), std::ios::ate | std::ios::binary);
        require(input.tellg() == static_cast<std::streamoff>(size), "RGBA8 file must be exactly width * height * 4 bytes");
        Bytes out(size);
        input.seekg(0);
        require(bool(input.read(reinterpret_cast<char *>(out.data()), out.size())), "cannot read RGBA8 input");
        return out;
    }
    Bytes out(size_t(width) * height * 4);
    uint32_t random = 0x23af940bu;
    for (size_t offset = 0; offset < out.size(); offset += 4) {
        random ^= random << 13;
        random ^= random >> 17;
        random ^= random << 5;
        for (uint32_t channel = 0; channel < 3; ++channel) {
            const auto byte = static_cast<unsigned char>(random >> (channel * 8));
            out[offset + channel] = pattern == "constant" ? (channel == 1 ? 255 : 0) : byte;
        }
        out[offset + 3] = 255;
    }
    return out;
}

static void write_bytes(const std::filesystem::path &path, const Bytes &bytes)
{
    std::ofstream file(path, std::ios::binary);
    require(bool(file.write(reinterpret_cast<const char *>(bytes.data()), bytes.size())), "cannot write readback");
}

struct Context {
    VkInstance instance{};
    VkDevice device{};
    ~Context()
    {
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
};

static void run(const std::filesystem::path &dir, uint32_t width, uint32_t height, std::string_view selector,
                std::string_view pattern, uint32_t repetitions, const std::filesystem::path &output,
                const std::filesystem::path &rewritten_spv)
{
    require(width >= 2 && height >= 2 && width <= 8192 && height <= 8192, "image dimension outside 2..8192");
    require(repetitions >= 2 && repetitions <= 128, "repeat count outside 2..128");
    require(!selector.empty(), "explicit Vulkan device name required");
    const bool compare_rewrite = !rewritten_spv.empty();
    Context context;
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "headless mipmap comparison";
    app.apiVersion = compare_rewrite ? VK_API_VERSION_1_3 : VK_API_VERSION_1_2;
    VkInstanceCreateInfo create_instance{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    create_instance.pApplicationInfo = &app;
    check(vkCreateInstance(&create_instance, nullptr, &context.instance), "vkCreateInstance");
    uint32_t physical_count{};
    check(vkEnumeratePhysicalDevices(context.instance, &physical_count, nullptr), "vkEnumeratePhysicalDevices");
    std::vector<VkPhysicalDevice> devices(physical_count);
    check(vkEnumeratePhysicalDevices(context.instance, &physical_count, devices.data()), "vkEnumeratePhysicalDevices");
    VkPhysicalDevice physical{};
    for (const auto candidate : devices) {
        VkPhysicalDeviceProperties properties{};
        vkGetPhysicalDeviceProperties(candidate, &properties);
        if (std::string_view(properties.deviceName).find(selector) == std::string_view::npos) continue;
        require(!physical, "device selector matched more than one device");
        physical = candidate;
    }
    require(physical, "requested Vulkan device not found");
    VkPhysicalDeviceSubgroupProperties subgroup{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
    VkPhysicalDeviceSubgroupSizeControlProperties size_control{
        VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_PROPERTIES};
    if (compare_rewrite) subgroup.pNext = &size_control;
    VkPhysicalDeviceProperties2 properties{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &subgroup};
    vkGetPhysicalDeviceProperties2(physical, &properties);
    require(properties.properties.apiVersion >= app.apiVersion, "required Vulkan API version unavailable");
    require(properties.properties.limits.timestampPeriod > 0, "Vulkan timestamp period unavailable");
    require(subgroup.subgroupSize == 32 && (subgroup.supportedOperations & VK_SUBGROUP_FEATURE_SHUFFLE_BIT) &&
            (subgroup.supportedStages & VK_SHADER_STAGE_COMPUTE_BIT), "this runner requires the upstream-tested Wave32 path");
    VkPhysicalDeviceVulkan13Features support13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    VkPhysicalDeviceVulkan13Features enable13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    if (compare_rewrite) {
        // https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineShaderStageRequiredSubgroupSizeCreateInfo.html
        VkPhysicalDeviceFeatures2 support{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &support13};
        vkGetPhysicalDeviceFeatures2(physical, &support);
        require(support13.subgroupSizeControl && support13.computeFullSubgroups &&
                size_control.minSubgroupSize <= 32 && size_control.maxSubgroupSize >= 32 &&
                (size_control.requiredSubgroupSizeStages & VK_SHADER_STAGE_COMPUTE_BIT) &&
                size_control.maxComputeWorkgroupSubgroups >= 8, "fixed full Wave32 contract unavailable");
        enable13.subgroupSizeControl = VK_TRUE;
        enable13.computeFullSubgroups = VK_TRUE;
    }
    VkPhysicalDeviceFeatures available{};
    vkGetPhysicalDeviceFeatures(physical, &available);
    require(available.shaderStorageImageArrayDynamicIndexing, "storage image dynamic array indexing unavailable");
    VkPhysicalDeviceFeatures features{};
    features.shaderStorageImageArrayDynamicIndexing = VK_TRUE;
    uint32_t queue_count{};
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, nullptr);
    std::vector<VkQueueFamilyProperties> families(queue_count);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, families.data());
    uint32_t family = 0;
    while (family < queue_count &&
           (!(families[family].queueFlags & VK_QUEUE_COMPUTE_BIT) || !families[family].timestampValidBits)) ++family;
    require(family < queue_count, "no timestamp-capable Vulkan compute queue");
    const float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = 1;
    queue_info.pQueuePriorities = &priority;
    VkDeviceCreateInfo create_device{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    if (compare_rewrite) create_device.pNext = &enable13;
    create_device.queueCreateInfoCount = 1;
    create_device.pQueueCreateInfos = &queue_info;
    create_device.pEnabledFeatures = &features;
    check(vkCreateDevice(physical, &create_device, nullptr, &context.device), "vkCreateDevice");
    const auto device = context.device;
    VkQueue queue{};
    vkGetDeviceQueue(device, family, 0, &queue);
    const uint32_t levels = static_cast<uint32_t>(std::bit_width(std::max(width, height)));
    const Bytes input = pixels(width, height, pattern);
    std::vector<VkBufferImageCopy> regions;
    VkDeviceSize payload_size{};
    for (uint32_t level = 1; level < levels; ++level) {
        const auto w = std::max(1u, width >> level);
        const auto h = std::max(1u, height >> level);
        VkBufferImageCopy region{};
        region.bufferOffset = input.size() + payload_size;
        region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, level, 0, 1};
        region.imageExtent = {w, h, 1};
        regions.push_back(region);
        payload_size += VkDeviceSize(w) * h * 4;
    }
    VkBufferCreateInfo buffer_info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    buffer_info.size = input.size() + payload_size;
    buffer_info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    VkBuffer staging{};
    check(vkCreateBuffer(device, &buffer_info, nullptr, &staging), "vkCreateBuffer");
    VkMemoryRequirements requirements{};
    vkGetBufferMemoryRequirements(device, staging, &requirements);
    VkDeviceMemory staging_memory = bind_memory(physical, device, requirements,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    check(vkBindBufferMemory(device, staging, staging_memory, 0), "vkBindBufferMemory");
    void *mapped{};
    check(vkMapMemory(device, staging_memory, 0, VK_WHOLE_SIZE, 0, &mapped), "vkMapMemory");
    auto *staging_bytes = static_cast<unsigned char *>(mapped);
    std::copy(input.begin(), input.end(), staging_bytes);

    constexpr VkFormat formats[]{VK_FORMAT_R8G8B8A8_SRGB, VK_FORMAT_R8G8B8A8_UINT};
    // https://docs.vulkan.org/refpages/latest/refpages/source/VkImageFormatListCreateInfo.html
    VkImageFormatListCreateInfo list{VK_STRUCTURE_TYPE_IMAGE_FORMAT_LIST_CREATE_INFO};
    list.viewFormatCount = std::size(formats);
    list.pViewFormats = formats;
    VkImageCreateInfo image_info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, &list};
    image_info.flags = VK_IMAGE_CREATE_MUTABLE_FORMAT_BIT | VK_IMAGE_CREATE_EXTENDED_USAGE_BIT;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = formats[0];
    image_info.extent = {width, height, 1};
    image_info.mipLevels = levels;
    image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_STORAGE_BIT |
                       VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    VkImage image{};
    check(vkCreateImage(device, &image_info, nullptr, &image), "vkCreateImage");
    vkGetImageMemoryRequirements(device, image, &requirements);
    VkDeviceMemory image_memory = bind_memory(physical, device, requirements, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    check(vkBindImageMemory(device, image, image_memory, 0), "vkBindImageMemory");

    const auto view = [&](VkFormat format, VkImageUsageFlags usage, uint32_t level, uint32_t count) {
        // https://docs.vulkan.org/refpages/latest/refpages/source/VkImageViewUsageCreateInfo.html
        VkImageViewUsageCreateInfo restriction{VK_STRUCTURE_TYPE_IMAGE_VIEW_USAGE_CREATE_INFO};
        restriction.usage = usage;
        VkImageViewCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, &restriction};
        info.image = image;
        info.viewType = VK_IMAGE_VIEW_TYPE_2D;
        info.format = format;
        info.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, level, count, 0, 1};
        VkImageView result{};
        check(vkCreateImageView(device, &info, nullptr, &result), "vkCreateImageView");
        return result;
    };
    const auto read_view = view(formats[0], VK_IMAGE_USAGE_SAMPLED_BIT, 0, levels);
    std::vector<VkImageView> write_views;
    for (uint32_t level = 0; level < levels; ++level)
        write_views.push_back(view(formats[1], VK_IMAGE_USAGE_STORAGE_BIT, level, 1));
    VkSamplerCreateInfo sampler_info{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
    sampler_info.magFilter = VK_FILTER_LINEAR;
    sampler_info.minFilter = VK_FILTER_LINEAR;
    sampler_info.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
    sampler_info.addressModeU = sampler_info.addressModeV = sampler_info.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    sampler_info.maxLod = float(levels - 1);
    VkSampler sampler{};
    check(vkCreateSampler(device, &sampler_info, nullptr, &sampler), "vkCreateSampler");

    const std::array<VkDescriptorType, 2> types{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE};
    const std::array<uint32_t, 2> counts{1, 16};
    std::array<VkDescriptorSetLayout, 2> layouts{};
    for (uint32_t i = 0; i < 2; ++i) {
        const VkDescriptorSetLayoutBinding binding{0, types[i], counts[i], VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
        VkDescriptorSetLayoutCreateInfo info{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        info.bindingCount = 1;
        info.pBindings = &binding;
        check(vkCreateDescriptorSetLayout(device, &info, nullptr, &layouts[i]), "vkCreateDescriptorSetLayout");
    }
    const std::array<VkDescriptorPoolSize, 2> pool_sizes{{{types[0], counts[0]}, {types[1], counts[1]}}};
    VkDescriptorPoolCreateInfo descriptor_pool_info{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    descriptor_pool_info.maxSets = 2;
    descriptor_pool_info.poolSizeCount = pool_sizes.size();
    descriptor_pool_info.pPoolSizes = pool_sizes.data();
    VkDescriptorPool descriptor_pool{};
    check(vkCreateDescriptorPool(device, &descriptor_pool_info, nullptr, &descriptor_pool), "vkCreateDescriptorPool");
    VkDescriptorSetAllocateInfo allocate_sets{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    allocate_sets.descriptorPool = descriptor_pool;
    allocate_sets.descriptorSetCount = 2;
    allocate_sets.pSetLayouts = layouts.data();
    std::array<VkDescriptorSet, 2> sets{};
    check(vkAllocateDescriptorSets(device, &allocate_sets, sets.data()), "vkAllocateDescriptorSets");
    VkDescriptorImageInfo read_image{sampler, read_view, VK_IMAGE_LAYOUT_GENERAL};
    std::array<VkDescriptorImageInfo, 16> write_images{};
    for (size_t i = 0; i < write_images.size(); ++i)
        write_images[i] = {VK_NULL_HANDLE, write_views[std::min(i, write_views.size() - 1)], VK_IMAGE_LAYOUT_GENERAL};
    std::array<VkWriteDescriptorSet, 2> updates{};
    for (uint32_t i = 0; i < 2; ++i) {
        updates[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        updates[i].dstSet = sets[i];
        updates[i].descriptorCount = counts[i];
        updates[i].descriptorType = types[i];
        updates[i].pImageInfo = i == 0 ? &read_image : write_images.data();
    }
    vkUpdateDescriptorSets(device, updates.size(), updates.data(), 0, nullptr);
    const VkPushConstantRange push{VK_SHADER_STAGE_COMPUTE_BIT, 0, 4};
    VkPipelineLayoutCreateInfo layout_info{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layout_info.setLayoutCount = 2;
    layout_info.pSetLayouts = layouts.data();
    layout_info.pushConstantRangeCount = 1;
    layout_info.pPushConstantRanges = &push;
    NvproPyramidPipelines general{};
    check(vkCreatePipelineLayout(device, &layout_info, nullptr, &general.layout), "vkCreatePipelineLayout");
    general.generalPipeline = make_pipeline(device, general.layout, dir / "general.spv", compare_rewrite);
    auto automatic = general;
    automatic.fastPipeline = make_pipeline(device, automatic.layout, dir / "fast.spv", compare_rewrite);
    auto rewritten = general;
    if (compare_rewrite) rewritten.fastPipeline = make_pipeline(device, rewritten.layout, rewritten_spv, true);
    const auto first = compare_rewrite ? automatic : general;
    const auto second = compare_rewrite ? rewritten : automatic;

    VkCommandPoolCreateInfo pool_info{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pool_info.queueFamilyIndex = family;
    VkCommandPool pool{};
    check(vkCreateCommandPool(device, &pool_info, nullptr, &pool), "vkCreateCommandPool");
    VkCommandBufferAllocateInfo alloc{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    alloc.commandPool = pool;
    alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc.commandBufferCount = 1;
    VkCommandBuffer commands{};
    check(vkAllocateCommandBuffers(device, &alloc, &commands), "vkAllocateCommandBuffers");
    VkQueryPoolCreateInfo query_info{VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO};
    query_info.queryType = VK_QUERY_TYPE_TIMESTAMP;
    query_info.queryCount = 4 * repetitions;
    VkQueryPool queries{};
    check(vkCreateQueryPool(device, &query_info, nullptr, &queries), "vkCreateQueryPool");
    const auto begin = [&] {
        check(vkResetCommandPool(device, pool, 0), "vkResetCommandPool");
        VkCommandBufferBeginInfo info{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(commands, &info), "vkBeginCommandBuffer");
    };
    const auto submit = [&] {
        check(vkEndCommandBuffer(commands), "vkEndCommandBuffer");
        VkSubmitInfo info{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        info.commandBufferCount = 1;
        info.pCommandBuffers = &commands;
        check(vkQueueSubmit(queue, 1, &info, VK_NULL_HANDLE), "vkQueueSubmit");
        check(vkQueueWaitIdle(queue), "vkQueueWaitIdle");
    };
    const auto barrier = [&](VkAccessFlags before, VkAccessFlags after,
                             VkPipelineStageFlags src, VkPipelineStageFlags dst,
                             VkImageLayout old_layout = VK_IMAGE_LAYOUT_GENERAL,
                             VkImageLayout new_layout = VK_IMAGE_LAYOUT_GENERAL) {
        VkImageMemoryBarrier info{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        info.srcAccessMask = before;
        info.dstAccessMask = after;
        info.oldLayout = old_layout;
        info.newLayout = new_layout;
        info.srcQueueFamilyIndex = info.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        info.image = image;
        info.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, levels, 0, 1};
        vkCmdPipelineBarrier(commands, src, dst, 0, 0, nullptr, 0, nullptr, 1, &info);
    };
    const auto bind = [&] {
        vkCmdBindDescriptorSets(commands, VK_PIPELINE_BIND_POINT_COMPUTE, general.layout,
                                0, sets.size(), sets.data(), 0, nullptr);
    };
    const auto dispatch = [&](NvproPyramidPipelines pipelines) {
        nvproCmdPyramidDispatch(commands, pipelines, width, height, levels);
    };
    const auto prepare_dispatch = [&] {
        barrier(VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_TRANSFER_READ_BIT,
                VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_SHADER_READ_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | VK_PIPELINE_STAGE_TRANSFER_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    };
    begin();
    barrier(0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    VkBufferImageCopy top{};
    top.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    top.imageExtent = {width, height, 1};
    vkCmdCopyBufferToImage(commands, staging, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &top);
    barrier(VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL);
    bind();
    for (uint32_t i = 0; i < 4; ++i) {
        prepare_dispatch();
        dispatch(i % 2 == 0 ? first : second);
    }
    // Same queue, same input, alternate order within each pair. Upload, readback and host work
    // are outside the intervals. https://docs.vulkan.org/samples/latest/samples/api/timestamp_queries/README.html
    vkCmdResetQueryPool(commands, queries, 0, query_info.queryCount);
    for (uint32_t i = 0; i < 2 * repetitions; ++i) {
        prepare_dispatch();
        const bool fast = (i % 2) != (i / 2 % 2);
        vkCmdWriteTimestamp(commands, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, queries, i * 2);
        dispatch(fast ? second : first);
        vkCmdWriteTimestamp(commands, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, queries, i * 2 + 1);
    }
    submit();
    std::vector<uint64_t> timestamps(query_info.queryCount);
    check(vkGetQueryPoolResults(device, queries, 0, query_info.queryCount,
          timestamps.size() * sizeof(uint64_t), timestamps.data(), sizeof(uint64_t),
          VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WAIT_BIT), "vkGetQueryPoolResults");
    const auto bits = families[family].timestampValidBits;
    const uint64_t mask = bits == 64 ? UINT64_MAX : (UINT64_C(1) << bits) - 1;
    std::cout << properties.properties.deviceName << " subgroup_property=" << subgroup.subgroupSize
              << " driver_raw=" << properties.properties.driverVersion << " timestamp_ns="
              << properties.properties.limits.timestampPeriod << " size=" << width << "x" << height
              << " fixed_full_wave32=" << compare_rewrite << '\n';
    for (uint32_t i = 0; i < 2 * repetitions; ++i) {
        const bool fast = (i % 2) != (i / 2 % 2);
        const auto tick = (timestamps[i * 2 + 1] - timestamps[i * 2]) & mask;
        const auto name = fast ? (compare_rewrite ? "rewritten" : "automatic")
                               : (compare_rewrite ? "automatic" : "general");
        std::cout << name << ',' << i / 2 << ','
                  << double(tick) * properties.properties.limits.timestampPeriod / 1e3 << '\n';
    }

    const auto readback = [&](NvproPyramidPipelines pipelines) {
        begin();
        // Keep a missing write in this variant visible instead of inheriting a prior result.
        const VkImageSubresourceRange generated{VK_IMAGE_ASPECT_COLOR_BIT, 1, levels - 1, 0, 1};
        const VkClearColorValue missing{{1.0f, 0.0f, 1.0f, 0.0f}};
        barrier(VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT,
                VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | VK_PIPELINE_STAGE_TRANSFER_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT);
        vkCmdClearColorImage(commands, image, VK_IMAGE_LAYOUT_GENERAL, &missing, 1, &generated);
        barrier(VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
        bind();
        dispatch(pipelines);
        barrier(VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
        vkCmdCopyImageToBuffer(commands, image, VK_IMAGE_LAYOUT_GENERAL, staging, regions.size(), regions.data());
        // https://docs.vulkan.org/guide/latest/synchronization_examples.html#cpu-read-back-of-data-written-by-a-compute-shader
        VkBufferMemoryBarrier host_read{VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER};
        host_read.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        host_read.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        host_read.srcQueueFamilyIndex = host_read.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        host_read.buffer = staging;
        host_read.offset = input.size();
        host_read.size = payload_size;
        vkCmdPipelineBarrier(commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                             0, 0, nullptr, 1, &host_read, 0, nullptr);
        submit();
        return Bytes(staging_bytes + input.size(), staging_bytes + input.size() + payload_size);
    };
    std::filesystem::create_directories(output);
    write_bytes(output / "base.rgba", input);
    write_bytes(output / "general.rgba", readback(general));
    write_bytes(output / "automatic.rgba", readback(automatic));
    if (compare_rewrite) write_bytes(output / "rewritten.rgba", readback(rewritten));

    vkDestroyQueryPool(device, queries, nullptr);
    vkDestroyCommandPool(device, pool, nullptr);
    if (compare_rewrite) vkDestroyPipeline(device, rewritten.fastPipeline, nullptr);
    vkDestroyPipeline(device, automatic.fastPipeline, nullptr);
    vkDestroyPipeline(device, general.generalPipeline, nullptr);
    vkDestroyPipelineLayout(device, general.layout, nullptr);
    vkDestroyDescriptorPool(device, descriptor_pool, nullptr);
    for (auto layout : layouts) vkDestroyDescriptorSetLayout(device, layout, nullptr);
    vkDestroySampler(device, sampler, nullptr);
    for (auto image_view : write_views) vkDestroyImageView(device, image_view, nullptr);
    vkDestroyImageView(device, read_view, nullptr);
    vkDestroyImage(device, image, nullptr);
    vkFreeMemory(device, image_memory, nullptr);
    vkUnmapMemory(device, staging_memory);
    vkDestroyBuffer(device, staging, nullptr);
    vkFreeMemory(device, staging_memory, nullptr);
}

int main(int argc, char **argv)
{
    if (argc != 8 && argc != 9) {
        std::cerr << "usage: mipmap SPV_DIR WIDTH HEIGHT DEVICE_SUBSTRING hashed|constant|RGBA8_FILE REPEATS OUTPUT_DIR [REWRITE_SPV]\n";
        return 2;
    }
    try {
        run(argv[1], std::stoul(argv[2]), std::stoul(argv[3]), argv[4], argv[5], std::stoul(argv[6]), argv[7],
            argc == 9 ? argv[8] : "");
    }
    catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
