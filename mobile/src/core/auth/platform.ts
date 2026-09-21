import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import type { SecureKeyValueStore } from "./identityVault";

const secureStoreOptions: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  keychainService: "jarvis.mobile.identity.v1",
};

export const expoSecureKeyValueStore: SecureKeyValueStore = {
  get: (key) => SecureStore.getItemAsync(key, secureStoreOptions),
  set: (key, value) => SecureStore.setItemAsync(key, value, secureStoreOptions),
  delete: (key) => SecureStore.deleteItemAsync(key, secureStoreOptions),
};

export interface RandomSource {
  bytes(length: number): Promise<Uint8Array>;
}

export const expoRandomSource: RandomSource = {
  bytes: (length) => Crypto.getRandomBytesAsync(length),
};
