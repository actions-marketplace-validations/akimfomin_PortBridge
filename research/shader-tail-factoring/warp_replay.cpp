// SPDX-License-Identifier: MIT
// Sample D3D12 pipeline creation and read back compiler test tuples.
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

template<class T>
class Com {
    T* value_ = nullptr;
public:
    Com() = default;
    Com(const Com&) = delete;
    Com& operator=(const Com&) = delete;
    ~Com() { if (value_) value_->Release(); }
    T** out() { return &value_; }
    T* operator->() const { return value_; }
    T* get() const { return value_; }
};

class Event {
    HANDLE value_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
public:
    Event() { if (!value_) throw std::runtime_error("CreateEventW failed"); }
    Event(const Event&) = delete;
    Event& operator=(const Event&) = delete;
    ~Event() { CloseHandle(value_); }
    HANDLE get() const { return value_; }
};

void check(HRESULT status, const char* operation) {
    if (FAILED(status)) {
        throw std::runtime_error(std::string(operation) + " HRESULT " +
                                 std::to_string(static_cast<std::uint32_t>(status)));
    }
}

std::vector<char> read_file(const char* path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error(std::string("cannot read ") + path);
    return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}

void make_buffer(ID3D12Device& device, std::uint64_t bytes, D3D12_HEAP_TYPE heap_type,
                 D3D12_RESOURCE_FLAGS flags, D3D12_RESOURCE_STATES initial_state,
                 Com<ID3D12Resource>& buffer) {
    D3D12_HEAP_PROPERTIES heap{};
    heap.Type = heap_type;
    heap.CreationNodeMask = 1;
    heap.VisibleNodeMask = 1;
    D3D12_RESOURCE_DESC layout{};
    layout.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    layout.Width = bytes;
    layout.Height = 1;
    layout.DepthOrArraySize = 1;
    layout.MipLevels = 1;
    layout.SampleDesc.Count = 1;
    layout.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    layout.Flags = flags;
    check(device.CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &layout, initial_state,
                                         nullptr, IID_PPV_ARGS(buffer.out())), "CreateCommittedResource");
}

using Clock = std::chrono::steady_clock;

void select_adapter(IDXGIFactory4& factory, bool physical, Com<IDXGIAdapter1>& adapter) {
    if (!physical) {
        check(factory.EnumWarpAdapter(IID_PPV_ARGS(adapter.out())), "EnumWarpAdapter");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if ((desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) == 0)
            throw std::runtime_error("expected WARP software adapter");
        return;
    }
    for (UINT ordinal = 0; ; ++ordinal) {
        Com<IDXGIAdapter1> candidate;
        const auto status = factory.EnumAdapters1(ordinal, candidate.out());
        if (status == DXGI_ERROR_NOT_FOUND) break;
        check(status, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(candidate->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId == 0x10de && (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) == 0 &&
            std::wstring(desc.Description) == L"NVIDIA GeForce RTX 4070 Ti SUPER") {
            check(factory.EnumAdapters1(ordinal, adapter.out()), "EnumAdapters1 select RTX");
            return;
        }
    }
    throw std::runtime_error("exact NVIDIA GeForce RTX 4070 Ti SUPER adapter is unavailable");
}

int replay(const char* shader_path, const char* inputs_path, const char* output_path,
           unsigned stride_words, bool physical) {
    const auto shader = read_file(shader_path);
    const auto inputs = read_file(inputs_path);
    const auto stride = sizeof(std::uint32_t) * stride_words;
    if (stride_words < 2 || stride_words > 32 || shader.empty() || inputs.empty() ||
        inputs.size() % (64 * stride) != 0 || inputs.size() / (64 * stride) > 65535) {
        throw std::runtime_error("expected complete 64-thread groups of u32 input tuples");
    }
    const auto threads = inputs.size() / stride;
    const auto output_bytes = threads * sizeof(std::uint32_t);

    Com<IDXGIFactory4> factory;
    Com<IDXGIAdapter1> adapter;
    Com<ID3D12Device> device;
    check(CreateDXGIFactory1(IID_PPV_ARGS(factory.out())), "CreateDXGIFactory1");
    select_adapter(*factory.get(), physical, adapter);
    check(D3D12CreateDevice(adapter.get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(device.out())),
          "D3D12CreateDevice");

    D3D12_ROOT_PARAMETER parameters[2]{};
    parameters[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
    parameters[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    D3D12_ROOT_SIGNATURE_DESC signature{};
    signature.NumParameters = 2;
    signature.pParameters = parameters;
    Com<ID3DBlob> serialized;
    Com<ID3D12RootSignature> root;
    check(D3D12SerializeRootSignature(&signature, D3D_ROOT_SIGNATURE_VERSION_1, serialized.out(), nullptr),
          "D3D12SerializeRootSignature");
    check(device->CreateRootSignature(0, serialized->GetBufferPointer(), serialized->GetBufferSize(),
                                      IID_PPV_ARGS(root.out())), "CreateRootSignature");
    D3D12_COMPUTE_PIPELINE_STATE_DESC pipeline_desc{};
    pipeline_desc.pRootSignature = root.get();
    pipeline_desc.CS = {shader.data(), shader.size()};
    Com<ID3D12PipelineState> pipeline;
    const auto begin = Clock::now();
    check(device->CreateComputePipelineState(&pipeline_desc, IID_PPV_ARGS(pipeline.out())),
          "CreateComputePipelineState");
    const auto pipeline_ms = std::chrono::duration<double, std::milli>(Clock::now() - begin).count();

    Com<ID3D12Resource> upload, output, readback;
    make_buffer(*device.get(), inputs.size(), D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_FLAG_NONE,
                D3D12_RESOURCE_STATE_GENERIC_READ, upload);
    make_buffer(*device.get(), output_bytes, D3D12_HEAP_TYPE_DEFAULT,
                D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_UNORDERED_ACCESS, output);
    make_buffer(*device.get(), output_bytes, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_FLAG_NONE,
                D3D12_RESOURCE_STATE_COPY_DEST, readback);
    const D3D12_RANGE no_reads{0, 0};
    void* mapped{};
    check(upload->Map(0, &no_reads, &mapped), "Map upload");
    std::memcpy(mapped, inputs.data(), inputs.size());
    upload->Unmap(0, nullptr);

    D3D12_COMMAND_QUEUE_DESC queue_desc{};
    queue_desc.Type = D3D12_COMMAND_LIST_TYPE_COMPUTE;
    Com<ID3D12CommandQueue> queue;
    Com<ID3D12CommandAllocator> commands;
    Com<ID3D12GraphicsCommandList> command_list;
    Com<ID3D12Fence> fence;
    check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(queue.out())), "CreateCommandQueue");
    check(device->CreateCommandAllocator(queue_desc.Type, IID_PPV_ARGS(commands.out())), "CreateCommandAllocator");
    check(device->CreateCommandList(0, queue_desc.Type, commands.get(), pipeline.get(),
                                    IID_PPV_ARGS(command_list.out())), "CreateCommandList");
    check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(fence.out())), "CreateFence");
    command_list->SetComputeRootSignature(root.get());
    command_list->SetComputeRootShaderResourceView(0, upload->GetGPUVirtualAddress());
    command_list->SetComputeRootUnorderedAccessView(1, output->GetGPUVirtualAddress());
    command_list->Dispatch(static_cast<UINT>(threads / 64), 1, 1);
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {output.get(), D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                          D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COPY_SOURCE};
    command_list->ResourceBarrier(1, &barrier);
    command_list->CopyBufferRegion(readback.get(), 0, output.get(), 0, output_bytes);
    check(command_list->Close(), "Close");
    ID3D12CommandList* submissions[] = {command_list.get()};
    Event done;
    const auto dispatch_begin = Clock::now();
    queue->ExecuteCommandLists(1, submissions);
    check(queue->Signal(fence.get(), 1), "Signal");
    check(fence->SetEventOnCompletion(1, done.get()), "SetEventOnCompletion");
    if (WaitForSingleObject(done.get(), 30000) != WAIT_OBJECT_0) {
        throw std::runtime_error("D3D12 compute did not complete");
    }
    const auto dispatch_ms = std::chrono::duration<double, std::milli>(Clock::now() - dispatch_begin).count();
    const D3D12_RANGE results{0, output_bytes};
    check(readback->Map(0, &results, &mapped), "Map readback");
    std::ofstream data(output_path, std::ios::binary);
    data.write(static_cast<const char*>(mapped), static_cast<std::streamsize>(output_bytes));
    readback->Unmap(0, &no_reads);
    data.close();
    if (!data) throw std::runtime_error("write replay output failed");
    std::cout << "{\"pso_ms\":" << pipeline_ms << ",\"dispatch_readback_ms\":" << dispatch_ms
              << ",\"threads\":" << threads << ",\"software\":" << (physical ? "false" : "true") << "}\n";
    return 0;
}

int main(int argc, char** argv) {
    try {
        if (argc != 6)
            throw std::runtime_error("usage: d3d12_replay shader.dxil tuples.bin output.bin stride_words adapter");
        const std::string adapter = argv[5];
        if (adapter != "warp" && adapter != "rtx4070ti-super") throw std::runtime_error("unknown adapter");
        return replay(argv[1], argv[2], argv[3], static_cast<unsigned>(std::stoul(argv[4])),
                      adapter == "rtx4070ti-super");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
