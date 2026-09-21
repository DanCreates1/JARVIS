import { StyleSheet, Text, View } from "react-native";

interface StatusBannerProps {
  detail: string;
  label: string;
  tone: "ready" | "offline";
}

export function StatusBanner({ detail, label, tone }: StatusBannerProps) {
  return (
    <View
      accessibilityLabel={`${label}. ${detail}`}
      accessibilityRole="summary"
      style={[styles.root, tone === "ready" ? styles.ready : styles.offline]}
    >
      <View style={[styles.indicator, tone === "ready" ? styles.readyDot : styles.offlineDot]} />
      <View style={styles.copy}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.detail}>{detail}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    alignItems: "center",
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    gap: 14,
    padding: 18,
  },
  ready: {
    backgroundColor: "#0b272d",
    borderColor: "#1d5c68",
  },
  offline: {
    backgroundColor: "#2b2412",
    borderColor: "#695629",
  },
  indicator: {
    borderRadius: 6,
    height: 12,
    width: 12,
  },
  readyDot: {
    backgroundColor: "#66e3ff",
  },
  offlineDot: {
    backgroundColor: "#f1c75b",
  },
  copy: {
    flex: 1,
    gap: 4,
  },
  label: {
    color: "#f4fbff",
    fontSize: 16,
    fontWeight: "700",
  },
  detail: {
    color: "#b5c7d0",
    fontSize: 14,
    lineHeight: 19,
  },
});
