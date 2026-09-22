import type { BarcodeScanningResult } from "expo-camera";
import { CameraView, useCameraPermissions } from "expo-camera";
import { Link, type Href } from "expo-router";
import { useEffect, useReducer, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { getMobileAuthClient } from "@/core/auth/runtime";
import { authReducer } from "@/core/auth/authState";
import type { DeviceIdentitySummary } from "@/core/auth/identityVault";
import { StatusBanner } from "@/ui/StatusBanner";

export interface PairingClient {
  restoreIdentity(): Promise<DeviceIdentitySummary | null>;
  pair(ticketPayload: string): Promise<{ identity: DeviceIdentitySummary }>;
  getStatus(): Promise<unknown>;
  logout(): Promise<void>;
  rotateKey(): Promise<{ identity: DeviceIdentitySummary }>;
  eraseCredentials(): Promise<void>;
}

export default function PairScreen({ authClient }: { authClient?: PairingClient } = {}) {
  const auth = authClient ?? getMobileAuthClient();
  const [state, dispatch] = useReducer(authReducer, { status: "loading" });
  const [ticket, setTicket] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{
    detail: string;
    tone: "ready" | "offline";
  } | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();

  useEffect(() => {
    let active = true;
    void auth
      .restoreIdentity()
      .then((identity) => {
        if (active) dispatch({ type: "RESTORED", identity });
      })
      .catch(() => {
        if (active)
          dispatch({ type: "FAILED", message: "Stored identity is unreadable. Erase it." });
      });
    return () => {
      active = false;
      setTicket("");
    };
  }, [auth]);

  async function pair(): Promise<void> {
    setStatusMessage(null);
    dispatch({ type: "PAIR_STARTED" });
    try {
      const result = await auth.pair(ticket);
      setTicket("");
      setScannerOpen(false);
      dispatch({ type: "PAIR_SUCCEEDED", identity: result.identity });
    } catch (error) {
      dispatch({
        type: "FAILED",
        message: error instanceof Error ? error.message : "Pairing failed",
      });
    }
  }

  async function openScanner(): Promise<void> {
    if (!permission?.granted) {
      const next = await requestPermission();
      if (!next.granted) {
        dispatch({
          type: "FAILED",
          message: "Camera permission denied. Paste ticket JSON instead.",
        });
        return;
      }
    }
    setScannerOpen(true);
  }

  function receiveBarcode(result: BarcodeScanningResult): void {
    setTicket(result.data);
    setScannerOpen(false);
  }

  async function erase(): Promise<void> {
    setStatusMessage(null);
    setCheckingStatus(true);
    try {
      await auth.eraseCredentials();
      dispatch({ type: "ERASED" });
    } catch {
      dispatch({
        type: "FAILED",
        message: "Local credentials erased. Remote revoke unavailable; revoke this device on Core.",
      });
    } finally {
      setTicket("");
      setScannerOpen(false);
      setCheckingStatus(false);
    }
  }

  async function checkStatus(): Promise<void> {
    setCheckingStatus(true);
    setStatusMessage(null);
    try {
      await auth.getStatus();
      setStatusMessage({ detail: "Core online. Signed status request passed.", tone: "ready" });
    } catch {
      setStatusMessage({
        detail: "Core unavailable or access revoked. Check Tailscale and Core.",
        tone: "offline",
      });
    } finally {
      setCheckingStatus(false);
    }
  }

  async function logout(): Promise<void> {
    setCheckingStatus(true);
    setStatusMessage(null);
    try {
      await auth.logout();
      setStatusMessage({ detail: "Session revoked. Device enrollment retained.", tone: "ready" });
    } catch {
      setStatusMessage({
        detail: "Session cleared locally. Remote revoke unavailable; revoke on Core.",
        tone: "offline",
      });
    } finally {
      setCheckingStatus(false);
    }
  }

  function confirmKeyRotation(): void {
    Alert.alert(
      "Rotate device key?",
      "Core will revoke existing sessions. Keep Core reachable until rotation finishes.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Rotate key", style: "destructive", onPress: () => void rotateKey() },
      ],
    );
  }

  async function rotateKey(): Promise<void> {
    setCheckingStatus(true);
    setStatusMessage(null);
    try {
      const result = await auth.rotateKey();
      dispatch({ type: "PAIR_SUCCEEDED", identity: result.identity });
      setStatusMessage({
        detail: "Device key rotated. Existing sessions were revoked.",
        tone: "ready",
      });
    } catch {
      setStatusMessage({
        detail: "Key rotation not confirmed. Reconnect to Core and retry status for recovery.",
        tone: "offline",
      });
    } finally {
      setCheckingStatus(false);
    }
  }

  const busy = state.status === "loading" || state.status === "pairing" || checkingStatus;

  return (
    <SafeAreaView style={styles.root}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.flex}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.heading}>
            <Text accessibilityRole="header" style={styles.title}>
              Pair with JARVIS Core
            </Text>
            <Text style={styles.copy}>
              Scan or paste the one-time enrollment ticket created on your trusted Core host.
            </Text>
          </View>

          {state.status === "loading" ? (
            <ActivityIndicator accessibilityLabel="Loading stored identity" color="#66e3ff" />
          ) : null}
          {state.status === "enrolled" ? (
            <StatusBanner
              detail={`Bound to ${state.identity.serverOrigin}`}
              label="Device enrolled"
              tone="ready"
            />
          ) : null}
          {state.status === "error" ? (
            <StatusBanner detail={state.message} label="Pairing unavailable" tone="offline" />
          ) : null}
          {statusMessage ? (
            <StatusBanner
              detail={statusMessage.detail}
              label="Core status"
              tone={statusMessage.tone}
            />
          ) : null}

          {state.status === "enrolled" ? (
            <View style={styles.actions}>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={() => void checkStatus()}
                style={styles.primaryButton}
              >
                <Text style={styles.primaryButtonText}>Check Core status</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={() => void logout()}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>Log out session</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={confirmKeyRotation}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>Rotate device key</Text>
              </Pressable>
            </View>
          ) : null}

          {scannerOpen ? (
            <View style={styles.scannerFrame}>
              <CameraView
                accessibilityLabel="Enrollment QR scanner"
                barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
                onBarcodeScanned={receiveBarcode}
                style={styles.camera}
              />
              <Pressable
                accessibilityRole="button"
                onPress={() => setScannerOpen(false)}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>Cancel scan</Text>
              </Pressable>
            </View>
          ) : state.status !== "enrolled" ? (
            <>
              <TextInput
                accessibilityLabel="Enrollment ticket JSON"
                autoCapitalize="none"
                autoCorrect={false}
                editable={!busy}
                multiline
                onChangeText={setTicket}
                placeholder="Paste enrollment ticket JSON"
                placeholderTextColor="#647b88"
                style={styles.input}
                value={ticket}
              />
              <View style={styles.actions}>
                <Pressable
                  accessibilityRole="button"
                  disabled={busy || ticket.trim().length === 0}
                  onPress={() => void pair()}
                  style={({ pressed }) => [
                    styles.primaryButton,
                    (busy || ticket.trim().length === 0) && styles.disabledButton,
                    pressed && styles.pressedButton,
                  ]}
                >
                  <Text style={styles.primaryButtonText}>
                    {state.status === "pairing" ? "Pairing…" : "Pair device"}
                  </Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  disabled={busy}
                  onPress={() => void openScanner()}
                  style={styles.secondaryButton}
                >
                  <Text style={styles.secondaryButtonText}>Scan QR</Text>
                </Pressable>
              </View>
            </>
          ) : null}

          <Text style={styles.securityNote}>
            Private key stays in device secure storage. Session tokens remain in memory. Changing
            Core origin requires a new enrollment.
          </Text>

          {state.status === "enrolled" || state.status === "error" ? (
            <Pressable
              accessibilityRole="button"
              disabled={busy}
              onPress={() => void erase()}
              style={styles.eraseButton}
            >
              <Text style={styles.eraseButtonText}>Erase local credentials</Text>
            </Pressable>
          ) : null}

          <Link href={"/" as Href} style={styles.backLink}>
            Back to launch screen
          </Link>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { backgroundColor: "#07141b", flex: 1 },
  flex: { flex: 1 },
  content: { gap: 18, padding: 24 },
  heading: { gap: 8, marginBottom: 6 },
  title: { color: "#f4fbff", fontSize: 28, fontWeight: "800" },
  copy: { color: "#b5c7d0", fontSize: 15, lineHeight: 22 },
  input: {
    backgroundColor: "#0d2029",
    borderColor: "#294653",
    borderRadius: 14,
    borderWidth: 1,
    color: "#f4fbff",
    minHeight: 150,
    padding: 16,
    textAlignVertical: "top",
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  primaryButton: {
    backgroundColor: "#66e3ff",
    borderRadius: 12,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  primaryButtonText: { color: "#05131a", fontSize: 15, fontWeight: "800" },
  secondaryButton: {
    borderColor: "#41616e",
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  secondaryButtonText: { color: "#d9eef7", fontSize: 15, fontWeight: "700" },
  disabledButton: { opacity: 0.45 },
  pressedButton: { opacity: 0.75 },
  securityNote: { color: "#8ca4b2", fontSize: 13, lineHeight: 19 },
  eraseButton: { alignSelf: "flex-start", paddingVertical: 8 },
  eraseButtonText: { color: "#ff9f9f", fontSize: 14, fontWeight: "700" },
  backLink: { color: "#66e3ff", fontSize: 15, marginTop: 8 },
  scannerFrame: { gap: 12 },
  camera: { aspectRatio: 1, borderRadius: 16, overflow: "hidden", width: "100%" },
});
