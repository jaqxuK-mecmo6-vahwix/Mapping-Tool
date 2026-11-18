import { describe, expect, it } from "vitest";
import { keyStep } from "../Controls";

describe("radius slider keyboard steps", () => {
  it("steps in the slider's rounding units and never gets stuck", () => {
    expect(keyStep(50, "ArrowRight")).toBe(51);
    expect(keyStep(50, "ArrowLeft")).toBe(49);
    expect(keyStep(9.5, "ArrowUp")).toBe(10);
    expect(keyStep(10, "ArrowUp")).toBe(11);
    expect(keyStep(10, "ArrowDown")).toBe(9.5);
    expect(keyStep(100, "ArrowUp")).toBe(105);
    expect(keyStep(100, "ArrowDown")).toBe(99);
    expect(keyStep(50.3, "ArrowRight")).toBe(51);
    expect(keyStep(50, "PageUp")).toBe(60);
    expect(keyStep(200, "PageDown")).toBe(150);
  });
  it("clamps to 1–500 km and ignores other keys", () => {
    expect(keyStep(1, "ArrowLeft")).toBe(1);
    expect(keyStep(500, "ArrowRight")).toBe(500);
    expect(keyStep(42, "Home")).toBe(1);
    expect(keyStep(42, "End")).toBe(500);
    expect(keyStep(42, "a")).toBeUndefined();
  });
  it("walks the whole range up and back without stalling", () => {
    let r = 1, n = 0;
    while (r < 500 && n < 1000) { r = keyStep(r, "ArrowRight")!; n++; }
    expect(r).toBe(500);
    while (r > 1 && n < 2000) { r = keyStep(r, "ArrowLeft")!; n++; }
    expect(r).toBe(1);
  });
});
