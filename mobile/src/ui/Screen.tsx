import type { PropsWithChildren } from "react";
import { StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { color, space } from "./tokens";

export function Screen({ children }: PropsWithChildren) {
  return <SafeAreaView style={styles.root}>{children}</SafeAreaView>;
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: color.canvas,
    flex: 1,
    paddingHorizontal: space.xl,
    paddingTop: space.xxl,
  },
});
