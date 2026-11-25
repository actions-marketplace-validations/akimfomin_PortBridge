// SPDX-License-Identifier: MIT
// Headless trace capture of pinned original SNOWFLOW CPU consumer functions.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";

const PIN = "545039733b74eec742862f161990142c7ca7c7ec";
const checkout = resolve(process.argv[2]);
const out = resolve(process.argv[3]);
const commit = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
if (commit !== PIN) throw new Error("unexpected SNOWFLOW commit " + commit);

const provenance = {};
function upstream(path) {
    const raw = execFileSync("git", ["-C", checkout, "show", PIN + ":" + path]);
    provenance[path] = createHash("sha256").update(raw).digest("hex");
    return raw.toString("utf8");
}

class Vector3 {
    constructor(x = 0, y = 0, z = 0) {
        this.set(x, y, z);
    }

    set(x, y, z) {
        this.x = x;
        this.y = y;
        this.z = z;
        return this;
    }

    copyFrom(other) {
        return this.set(other.x, other.y, other.z);
    }

    normalize() {
        const length = Math.hypot(this.x, this.y, this.z);
        if (length) this.set(this.x / length, this.y / length, this.z / length);
        return this;
    }
}

function localImportsOnly(source) {
    return source.replace(/^import [^\r\n]+;\r?\n/gm, "").replace(/^export /gm, "");
}

const input = { moveX: 0, moveZ: 0, surf: false, sprint: false };
const context = vm.createContext({
    console, Float32Array, Vector3, input,
    Scalar: { Clamp: (value, lo, hi) => Math.min(hi, Math.max(lo, value)) },
});
let cameraSource = upstream("src/core/camera.js");
const expDamp = cameraSource.match(/export function expDamp[\s\S]*?\n\}/);
if (!expDamp) throw new Error("upstream damping function not located");
vm.runInContext(localImportsOnly(expDamp[0]), context);
vm.runInContext(localImportsOnly(upstream("src/terrain/heightfield.js")), context);
vm.runInContext(localImportsOnly(upstream("src/character/controller.js")), context);
const heightfield = vm.runInContext("Object.create(Heightfield.prototype)", context);
const heightRes = vm.runInContext("HEIGHT_RES", context);
const worldSize = vm.runInContext("WORLD_SIZE", context);
heightfield.origin = { x: -worldSize / 2, y: -worldSize / 2 };
heightfield.size = worldSize;

const readbackCalls = [];
let raw = new Float32Array(heightRes * heightRes * 2);
for (let y = 0; y < heightRes; y++) {
    for (let x = 0; x < heightRes; x++) {
        raw[2 * (y * heightRes + x)] = 0.002 * x + 0.004 * y;
    }
}
heightfield.heightTex = {
    async readPixels(face, mip) {
        readbackCalls.push({ face, mip, format: "RG32F", bytes: raw.byteLength });
        return raw;
    },
};
await heightfield._readback();
if (readbackCalls.length !== 1 || heightfield.cpuRes !== heightRes / 2 ||
        !Number.isFinite(heightfield.minHeight) || heightfield.maxHeight <= heightfield.minHeight) {
    throw new Error("The stock CPU readback handler failed its control");
}
raw = null;

let touched = null;
let accesses = 0;
const heightCPU = heightfield.heightCPU;
heightfield.heightCPU = new Proxy(heightCPU, {
    get(target, key) {
        if (typeof key === "string" && /^(0|[1-9][0-9]*)$/.test(key)) {
            const word = Number(key);
            if (word >= target.length || touched === null) throw new Error("unexpected sample index");
            touched.add(word);
            accesses++;
        }
        return Reflect.get(target, key, target);
    },
});

function captureRoute(holdout) {
    const character = new (vm.runInContext("CharacterController", context))(heightfield);
    if (holdout) character.position.set(167, 0, 116);
    const rig = {
        yaw: 0,
        getFlatForward(out) { return out.set(Math.sin(this.yaw), 0, Math.cos(this.yaw)); },
        getFlatRight(out) { return out.set(Math.cos(this.yaw), 0, -Math.sin(this.yaw)); },
        addTrauma() {},
    };
    const frames = [];
    for (let i = 0; i < 240; i++) {
        touched = new Set();
        accesses = 0;
        rig.yaw = holdout ? 0.9 + i / 220 : 0.05 + i / 600;
        input.moveX = holdout && i >= 125 ? -0.35 : 0;
        input.moveZ = i >= 205 ? -0.4 : 1;
        input.sprint = i >= 50 && i < 115;
        input.surf = i >= 115 && i < 200;
        character.update(1 / 60, rig);
        if (!Number.isFinite(character.groundY) || touched.size === 0) {
            throw new Error("invalid grounded frame " + i);
        }
        frames.push({
            epoch: i,
            accesses,
            words: [...touched].sort((a, b) => a - b),
            samples: [character.position.x, character.position.z].map((n) => Number(n.toFixed(8))),
        });
        touched = null;
    }
    return frames;
}
const routes = {
    "snowflow-grounding": captureRoute(false),
    "snowflow-grounding-holdout": captureRoute(true),
};
writeFileSync(out, JSON.stringify({
    source: "https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/tree/" + PIN,
    license: "MIT", provenance, readbackCalls, cpuMirrorBytes: heightCPU.byteLength,
    routes,
}) + "\n", "utf8");
console.log(readbackCalls.length, "stock readback", readbackCalls[0].bytes, "bytes");
for (const [name, frames] of Object.entries(routes)) {
    const total = frames.reduce((sum, item) => sum + item.accesses, 0);
    const union = new Set(frames.flatMap((frame) => frame.words.map((word) => Math.floor(word / 1024))));
    console.log(name, frames.length, "frames", total, "sample loads", union.size, "unique 4KiB pages");
}
