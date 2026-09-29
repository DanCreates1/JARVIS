import { StyleSheet, Text, View } from "react-native";

import { EmptyState } from "@/ui/EmptyState";
import { Screen } from "@/ui/Screen";
import { color, space } from "@/ui/tokens";

export default function GarminScreen() {
  return (
    <Screen>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Garmin
        </Text>
        <EmptyState
          title="No Garmin data connected"
          detail="Garmin setup and read-only summaries arrive in Mobile MVP 3."
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: space.lg },
  title: { color: color.text, fontSize: 32, fontWeight: "800" },
});
