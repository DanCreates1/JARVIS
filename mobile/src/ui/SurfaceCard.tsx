import type { PropsWithChildren } from "react";
import { StyleSheet, View } from "react-native";

import { color, radius, space } from "./tokens";

export function SurfaceCard({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: color.surface,
    borderColor: color.border,
    borderRadius: radius.card,
    borderWidth: 1,
    gap: space.md,
    padding: space.lg,
  },
});
