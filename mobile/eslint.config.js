const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");
const typescriptResolver = require.resolve("eslint-import-resolver-typescript");

module.exports = defineConfig([
  ...expoConfig,
  {
    ignores: [".expo/**", "dist/**", "node_modules/**", "expo-env.d.ts"],
    settings: {
      "import/resolver": {
        [typescriptResolver]: {
          alwaysTryTypes: true,
          project: "./tsconfig.json",
        },
      },
    },
  },
]);
