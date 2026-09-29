import { StyleSheet, Text, View } from "react-native";

import { color, space } from "./tokens";
import { SurfaceCard } from "./SurfaceCard";

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <SurfaceCard>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        <Text style={styles.detail}>{detail}</Text>
      </View>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  content: { gap: space.sm },
  title: { color: color.text, fontSize: 20, fontWeight: "700" },
  detail: { color: color.muted, fontSize: 16, lineHeight: 24 },
});
