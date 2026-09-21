import { StyleSheet, Text, View } from "react-native";

import { readAppConfig } from "@/config/appConfig";
import { Screen } from "@/ui/Screen";
import { StatusBanner } from "@/ui/StatusBanner";

export default function IndexScreen() {
  const config = readAppConfig();

  return (
    <Screen>
      <View style={styles.brand}>
        <View accessibilityElementsHidden style={styles.mark}>
          <Text style={styles.markText}>J</Text>
        </View>
        <Text accessibilityRole="header" style={styles.title}>
          JARVIS
        </Text>
        <Text style={styles.subtitle}>Native foundation</Text>
      </View>

      <StatusBanner
        label="Foundation ready"
        detail="Offline-safe shell. No Core connection configured."
        tone="ready"
      />

      <View style={styles.details}>
        <Text style={styles.detailLabel}>Environment</Text>
        <Text style={styles.detailValue}>{config.environment}</Text>
        <Text style={styles.note}>
          Authentication, remote APIs, telemetry, and device permissions are not active.
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brand: {
    alignItems: "center",
    gap: 8,
    marginBottom: 36,
  },
  mark: {
    alignItems: "center",
    backgroundColor: "#66e3ff",
    borderRadius: 18,
    height: 72,
    justifyContent: "center",
    marginBottom: 8,
    shadowColor: "#66e3ff",
    shadowOpacity: 0.35,
    shadowRadius: 18,
    width: 72,
  },
  markText: {
    color: "#05131a",
    fontSize: 38,
    fontWeight: "800",
  },
  title: {
    color: "#f4fbff",
    fontSize: 36,
    fontWeight: "800",
    letterSpacing: 8,
  },
  subtitle: {
    color: "#8ca4b2",
    fontSize: 15,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  details: {
    borderColor: "#203742",
    borderRadius: 16,
    borderWidth: 1,
    gap: 6,
    marginTop: 18,
    padding: 18,
  },
  detailLabel: {
    color: "#8ca4b2",
    fontSize: 12,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  detailValue: {
    color: "#f4fbff",
    fontSize: 18,
    fontWeight: "600",
    textTransform: "capitalize",
  },
  note: {
    color: "#8ca4b2",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 10,
  },
});
