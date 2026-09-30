import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    // The app should render without throwing.
    expect(document.body).toBeTruthy();
  });
});
