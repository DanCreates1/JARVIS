import { Tabs } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { color, touchTarget } from "@/ui/tokens";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: color.accent,
          tabBarInactiveTintColor: color.muted,
          tabBarLabelStyle: { fontSize: 14, fontWeight: "700" },
          tabBarStyle: {
            backgroundColor: color.surface,
            borderTopColor: color.border,
            minHeight: 64,
          },
          tabBarItemStyle: { minHeight: touchTarget },
        }}
      >
        <Tabs.Screen name="index" options={{ title: "Chat", tabBarAccessibilityLabel: "Chat" }} />
        <Tabs.Screen
          name="garmin"
          options={{ title: "Garmin", tabBarAccessibilityLabel: "Garmin" }}
        />
        <Tabs.Screen
          name="settings"
          options={{ title: "Settings", tabBarAccessibilityLabel: "Settings" }}
        />
        <Tabs.Screen name="pair" options={{ href: null }} />
      </Tabs>
    </SafeAreaProvider>
  );
}
