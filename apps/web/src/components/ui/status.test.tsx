import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Status } from "./status";

describe("Status", () => {
  it("renders a localized success status", () => {
    render(<Status value="completed" />);
    expect(screen.getByText("已完成")).toHaveClass("status-success");
  });

  it("keeps unknown status values observable", () => {
    render(<Status value="queued" />);
    expect(screen.getByText("queued")).toHaveClass("status-neutral");
  });
});
