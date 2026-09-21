import { readAppConfig } from "@/config/appConfig";
import { SignedApiClient } from "@/core/api/signedApiClient";
import type { FetchLike } from "@/core/api/types";

import { MobileAuthClient } from "./authClient";
import { IdentityVault } from "./identityVault";
import { expoRandomSource, expoSecureKeyValueStore } from "./platform";

const fetchAdapter: FetchLike = async (input, init) =>
  fetch(input, {
    method: init.method,
    headers: { ...init.headers },
    ...(init.body === undefined ? {} : { body: init.body }),
  });

let singleton: MobileAuthClient | null = null;

export function getMobileAuthClient(): MobileAuthClient {
  if (singleton === null) {
    const allowInsecureLoopback = __DEV__ && readAppConfig().environment === "development";
    const options = { allowInsecureLoopback };
    const vault = new IdentityVault(expoSecureKeyValueStore, options);
    const api = new SignedApiClient(fetchAdapter, expoRandomSource);
    singleton = new MobileAuthClient(vault, api, expoRandomSource, undefined, options);
  }
  return singleton;
}
