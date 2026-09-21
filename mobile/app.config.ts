import type { ConfigContext, ExpoConfig } from "expo/config";

const APP_ENVIRONMENTS = ["development", "preview", "production"] as const;

function appEnvironment(): (typeof APP_ENVIRONMENTS)[number] {
  const value = process.env.EXPO_PUBLIC_JARVIS_ENV ?? "development";

  if (!APP_ENVIRONMENTS.includes(value as (typeof APP_ENVIRONMENTS)[number])) {
    throw new Error(
      `EXPO_PUBLIC_JARVIS_ENV must be one of ${APP_ENVIRONMENTS.join(", ")}; received ${value}`,
    );
  }

  return value as (typeof APP_ENVIRONMENTS)[number];
}

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "JARVIS",
  slug: "jarvis-mobile",
  version: "0.1.0",
  orientation: "portrait",
  userInterfaceStyle: "automatic",
  plugins: ["expo-router"],
  experiments: {
    typedRoutes: true,
  },
  ios: {
    supportsTablet: true,
  },
  android: {},
  extra: {
    appEnvironment: appEnvironment(),
  },
});
