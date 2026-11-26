// SPDX-License-Identifier: MIT
// Records GPU command requests from the pinned upstream methods on a fake device.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { stripTypeScriptTypes } from "node:module";
import { writeFileSync } from "node:fs";
import vm from "node:vm";

const PIN = "8d6bcecb643772730fc1ebacd3e0eba2aea7066c";
const checkout = process.argv[2];
const output = process.argv[3];
const rev = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
if (rev !== PIN) throw new Error("unexpected HeatTransfer commit " + rev);
const digest = {};
function load(path) {
    const raw = execFileSync("git", ["-C", checkout, "show", PIN + ":" + path]);
    digest[path] = createHash("sha256").update(raw).digest("hex");
    return raw.toString("utf8").replace(/\r\n/g, "\n");
}
function method(text, start, end) {
    const i = text.indexOf(start);
    const j = text.indexOf(end, i + start.length);
    if (i < 0 || j < 0) throw new Error("pinned method boundary missing");
    return text.slice(i, j).trimEnd();
}
const constants = load("src/HeatTransferConstants.ts");
const every = Number(constants.match(/READBACK_FRAME_INTERVAL = (\d+);/)[1]);
const presets = {
    classroom: Number(constants.match(/classroom: (\d+),/)[1]),
    extreme: Number(constants.match(/extreme: (\d+),/)[1]),
};
const upstream = load("src/common/field/gpu/WebGpuFieldEngine.ts");
const members = method(upstream, "  public step(", "  private writeSimParams(") +
    "\n" + method(upstream, "  private requestReadback():", "  // ── Rendering");
const scratch = vm.createContext({ READBACK_FRAME_INTERVAL: every, GPUMapMode: { READ: 1 }, Float32Array });
vm.runInContext(stripTypeScriptTypes("class ExtractedEngine {\n" + members + "\n}", {
    mode: "strip",
}), scratch);
const Engine = vm.runInContext("ExtractedEngine", scratch);

async function capture(size, deferred) {
    const periods = [];
    let current;
    let tick = 0;
    const resolves = [];
    const engine = new Engine();
    const readback = new ArrayBuffer(4 * size * size);
    const pass = {
        setPipeline() {},
        setBindGroup() {},
        dispatchWorkgroups(x, y) { current.dispatches.push([x, y]); },
        end() {},
    };
    engine.device = {
        queue: { submit() { current.submissions++; } },
        createCommandEncoder() {
            return {
                beginComputePass() { return pass; },
                copyTextureToBuffer(src, dst, extent) {
                    current.readbacks.push({
                        texture: src.texture,
                        width: extent.width, height: extent.height,
                        bytesPerRow: dst.bytesPerRow,
                        bytes: dst.bytesPerRow * extent.height,
                    });
                },
                finish() {},
            };
        },
    };
    engine.domain = { gridWidth: size, gridHeight: size };
    engine.current = 0;
    engine.frameCounter = 0;
    engine.elapsedTime = 0;
    engine.computeSubstep = () => 1 / 60;
    engine.writeSimParams = () => {};
    engine.workgroupsX = () => Math.ceil(size / 8);
    engine.workgroupsY = () => Math.ceil(size / 8);
    engine.diffuseBindGroups = [0, 1];
    engine.temperatureTextures = [0, 1];
    engine.temperatureMirror = new Float32Array(size * size);
    engine.readbackBuffer = {
        mapAsync: () => new Promise((resolve) => resolves.push({ due: tick + deferred, resolve })),
        getMappedRange: () => readback,
        unmap() {},
    };

    for (tick = 0; tick < 48; tick++) {
        current = { epoch: tick, dispatches: [], readbacks: [], submissions: 0 };
        engine.step({
            substeps: 1, diffusionEnabled: true, diffusionScale: 1,
            advectionEnabled: false, flowScale: 0, boundaryCondition: "reflect",
        });
        periods.push(current);
        for (const item of resolves) if (item.due === tick) item.resolve();
        await new Promise((resolve) => setImmediate(resolve));
    }
    for (const item of resolves) item.resolve();
    await new Promise((resolve) => setImmediate(resolve));
    for (const frame of periods) {
        if (frame.dispatches.length !== 1 || frame.readbacks.length > 1 ||
                frame.readbacks.some((item) => item.bytes !== 4 * size * size)) {
            throw new Error("unexpected pinned command sequence");
        }
    }
    return periods;
}
const captures = {};
for (const [name, size, latency] of [
    ["heat-classroom", presets.classroom, 0],
    ["heat-extreme", presets.extreme, 0],
    ["heat-extreme-busy", presets.extreme, 5],
]) {
    const frames = await capture(size, latency);
    captures[name] = { size, assumedMapDelayFrames: latency, frames };
    console.log(name, frames.length, "writes,", frames.flatMap((f) => f.readbacks).length, "readbacks");
}
writeFileSync(output, JSON.stringify({
    source: "https://github.com/OpenLyceum/HeatTransfer/tree/" + PIN,
    license: "AGPL-3.0-or-later", digest, every, captures,
}) + "\n", "utf8");
