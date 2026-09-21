import Constants from "expo-constants";

export const APP_ENVIRONMENTS = ["development", "preview", "production"] as const;

export type AppEnvironment = (typeof APP_ENVIRONMENTS)[number];

export interface AppConfig {
  environment: AppEnvironment;
}

export function parseAppEnvironment(value: unknown): AppEnvironment {
  if (typeof value !== "string" || !APP_ENVIRONMENTS.includes(value as AppEnvironment)) {
    return "development";
  }

  return value as AppEnvironment;
}

export function readAppConfig(): AppConfig {
  return {
    environment: parseAppEnvironment(Constants.expoConfig?.extra?.appEnvironment),
  };
}
