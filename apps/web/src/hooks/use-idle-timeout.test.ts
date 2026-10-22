import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IDLE_TIMEOUT_MS, IDLE_WARNING_MS, useIdleTimeout } from "./use-idle-timeout";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-21T08:00:00Z"));
});
afterEach(() => vi.useRealTimers());

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

describe("useIdleTimeout", () => {
  it("warns at 14 minutes with a 60 second countdown, then times out at 15", () => {
    const onTimeout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout(onTimeout));
    advance(IDLE_TIMEOUT_MS - IDLE_WARNING_MS - 1000);
    expect(result.current.warning).toBe(false);
    advance(2000);
    expect(result.current.warning).toBe(true);
    expect(result.current.secondsLeft).toBeLessThanOrEqual(60);
    expect(onTimeout).not.toHaveBeenCalled();
    advance(IDLE_WARNING_MS);
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it("activity before the warning resets the timer", () => {
    const onTimeout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout(onTimeout));
    advance(10 * 60 * 1000);
    act(() => {
      window.dispatchEvent(new Event("keydown"));
    });
    advance(10 * 60 * 1000);
    expect(result.current.warning).toBe(false);
    expect(onTimeout).not.toHaveBeenCalled();
  });

  it("activity during the warning does not dismiss it, but stay() does", () => {
    const onTimeout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout(onTimeout));
    advance(IDLE_TIMEOUT_MS - 30_000);
    act(() => {
      window.dispatchEvent(new Event("pointermove"));
    });
    advance(1000);
    expect(result.current.warning).toBe(true);
    act(() => result.current.stay());
    expect(result.current.warning).toBe(false);
    advance(IDLE_TIMEOUT_MS - IDLE_WARNING_MS - 1000);
    expect(onTimeout).not.toHaveBeenCalled();
  });

  it("does nothing when disabled", () => {
    const onTimeout = vi.fn();
    renderHook(() => useIdleTimeout(onTimeout, { enabled: false }));
    advance(IDLE_TIMEOUT_MS * 2);
    expect(onTimeout).not.toHaveBeenCalled();
  });
});
