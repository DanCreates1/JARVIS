import type { ReactElement } from "react";
import { render } from "@testing-library/react-native";

export function renderApp(element: ReactElement) {
  return render(element);
}
