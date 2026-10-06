import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  isDeviceAuthorizationState,
  isPairingState,
  isDevicePairResponse,
  type DeviceAuthorizationState,
  type PairingState,
  type DevicePairResponse,
} from "../types";
import {
  isConnectedDevice,
  pairDevice,
  type ConnectedDevice,
} from "../devices";
import * as requestModule from "../request";

describe("iOS types and validation guards", () => {
  it("validates valid DeviceAuthorizationState values", () => {
    const validStates: DeviceAuthorizationState[] = [
      "UNKNOWN",
      "AUTHORIZED",
      "AUTHORIZATION_REQUIRED",
      "RESTRICTED",
    ];

    for (const state of validStates) {
      expect(isDeviceAuthorizationState(state)).toBe(true);
    }

    expect(isDeviceAuthorizationState("INVALID_STATE")).toBe(false);
    expect(isDeviceAuthorizationState("")).toBe(false);
    expect(isDeviceAuthorizationState(null)).toBe(false);
    expect(isDeviceAuthorizationState(undefined)).toBe(false);
    expect(isDeviceAuthorizationState(123)).toBe(false);
  });

  it("validates valid PairingState values", () => {
    const validStates: PairingState[] = [
      "PAIRED",
      "ALREADY_PAIRED",
      "USER_ACTION_REQUIRED",
      "RESTRICTED",
      "DEVICE_DISCONNECTED",
      "INCONCLUSIVE",
      "ERROR",
    ];

    for (const state of validStates) {
      expect(isPairingState(state)).toBe(true);
    }

    expect(isPairingState("FAILED")).toBe(false);
    expect(isPairingState("UNKNOWN")).toBe(false);
    expect(isPairingState("")).toBe(false);
    expect(isPairingState(null)).toBe(false);
    expect(isPairingState({})).toBe(false);
  });

  it("validates valid DevicePairResponse objects", () => {
    const validResp: DevicePairResponse = {
      device_id: "ios-123456",
      status: "PAIRED",
      message: "Device paired successfully.",
    };

    expect(isDevicePairResponse(validResp)).toBe(true);
    expect(
      isDevicePairResponse({
        ...validResp,
        status: "USER_ACTION_REQUIRED",
      })
    ).toBe(true);

    // Invalid / missing fields
    expect(isDevicePairResponse(null)).toBe(false);
    expect(isDevicePairResponse({})).toBe(false);
    expect(isDevicePairResponse({ device_id: "ios-1", status: "PAIRED" })).toBe(
      false
    );
    expect(
      isDevicePairResponse({
        device_id: "ios-1",
        status: "INVALID_STATUS",
        message: "test",
      })
    ).toBe(false);
  });

  it("validates ConnectedDevice with optional authorization_state", () => {
    const iosDevice: ConnectedDevice = {
      device_id: "ios-abc1234",
      platform: "IOS",
      connection_state: "CONNECTED",
      authorization_state: "AUTHORIZED",
      identity: null,
    };

    expect(isConnectedDevice(iosDevice)).toBe(true);

    const androidDevice: ConnectedDevice = {
      device_id: "android-xyz987",
      platform: "ANDROID",
      connection_state: "CONNECTED",
      identity: null,
    };

    expect(isConnectedDevice(androidDevice)).toBe(true);

    // Malformed authorization_state
    expect(
      isConnectedDevice({
        ...iosDevice,
        authorization_state: "INVALID_AUTH",
      })
    ).toBe(false);
  });

  describe("pairDevice client API function", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it("successfully issues POST /api/v1/devices/{device_id}/pair", async () => {
      const mockResponse: DevicePairResponse = {
        device_id: "ios-test-1",
        status: "PAIRED",
        message: "Device paired.",
      };

      vi.spyOn(requestModule, "safeFetchJson").mockResolvedValue({
        ok: true,
        data: mockResponse,
      });

      const result = await pairDevice("ios-test-1");
      expect(result.data).toEqual(mockResponse);
      expect(result.errorMessage).toBeNull();
      expect(requestModule.safeFetchJson).toHaveBeenCalledWith(
        "/api/v1/devices/ios-test-1/pair",
        isDevicePairResponse,
        expect.objectContaining({ method: "POST" })
      );
    });

    it("returns error result if safeFetchJson fails", async () => {
      vi.spyOn(requestModule, "safeFetchJson").mockResolvedValue({
        ok: false,
        error: {
          kind: "HTTP",
          message: "Device is locked with a passcode.",
          statusCode: 400,
        },
      });

      const result = await pairDevice("ios-test-1");
      expect(result.data).toBeNull();
      expect(result.errorMessage).toBe("Device is locked with a passcode.");
      expect(result.error?.statusCode).toBe(400);
    });
  });
});
