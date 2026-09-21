import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import { expoRandomSource, expoSecureKeyValueStore } from "@/core/auth/platform";

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock("expo-crypto", () => ({
  getRandomBytesAsync: jest.fn(),
}));

describe("native secure platform adapters", () => {
  it("uses device-only SecureStore options for every identity operation", async () => {
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue("stored");
    await expect(expoSecureKeyValueStore.get("identity")).resolves.toBe("stored");
    await expoSecureKeyValueStore.set("identity", "value");
    await expoSecureKeyValueStore.delete("identity");

    const options = {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      keychainService: "jarvis.mobile.identity.v1",
    };
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith("identity", options);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith("identity", "value", options);
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("identity", options);
  });

  it("delegates entropy generation to Expo Crypto", async () => {
    const bytes = Uint8Array.from([1, 2, 3, 4]);
    jest.mocked(Crypto.getRandomBytesAsync).mockResolvedValue(bytes);
    await expect(expoRandomSource.bytes(4)).resolves.toEqual(bytes);
    expect(Crypto.getRandomBytesAsync).toHaveBeenCalledWith(4);
  });
});
