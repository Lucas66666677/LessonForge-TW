import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LucirelProductBrand } from "./LucirelProductBrand";

describe("LucirelProductBrand", () => {
  it("renders the canonical company endorsement", () => {
    render(<LucirelProductBrand />);

    expect(
      screen.getByRole("img", { name: "Lucirel Wave Gate" }),
    ).toBeInTheDocument();
    expect(screen.getByText("LessonForge")).toBeInTheDocument();
    expect(screen.getByText(/by Lucirel/)).toBeInTheDocument();
  });
});
