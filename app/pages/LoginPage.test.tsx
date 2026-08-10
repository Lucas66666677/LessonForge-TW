import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("validates the email before submitting", async () => {
    const user = userEvent.setup();
    render(<LoginPage onLogin={vi.fn()} />);
    const email = screen.getByLabelText("Email");
    await user.clear(email);
    await user.type(email, "not-an-email");
    await user.click(screen.getByRole("button", { name: "進入 LessonForge" }));
    expect(await screen.findByText("請輸入有效 Email")).toBeInTheDocument();
  });

  it("returns a token after successful Demo login", async () => {
    const onLogin = vi.fn();
    vi.spyOn(api, "login").mockResolvedValue({
      access_token: "demo-token",
      user: {
        id: "u1",
        email: "owner@demo.lessonforge.tw",
        display_name: "Owner",
        organization_id: "o1",
        organization_name: "Demo",
        role: "owner",
      },
    });
    render(<LoginPage onLogin={onLogin} />);
    fireEvent.submit(
      screen.getByRole("button", { name: "進入 LessonForge" }).closest("form")!,
    );
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith("demo-token"));
  });
});
