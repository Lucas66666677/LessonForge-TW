import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type CurrentUser } from "../lib/api";
import { ErrorState, LoadingState } from "../components/ui";
import { MembersPage } from "./MembersPage";

const teacher: CurrentUser = {
  id: "u1",
  email: "teacher@example.com",
  display_name: "Teacher",
  organization_id: "o1",
  organization_name: "Demo",
  role: "teacher",
};

describe("states and role differences", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders complete loading and error states", () => {
    const { rerender } = render(<LoadingState label="載入教材…" />);
    expect(screen.getByRole("status")).toHaveTextContent("載入教材");
    rerender(<ErrorState message="網路錯誤" />);
    expect(screen.getByRole("alert")).toHaveTextContent("網路錯誤");
  });

  it("hides member creation for teacher role", async () => {
    vi.spyOn(api, "members").mockResolvedValue([
      {
        id: "u1",
        email: teacher.email,
        display_name: teacher.display_name,
        role: "teacher",
      },
    ]);
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <MembersPage
            token="token"
            currentUser={teacher}
            onTokenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Teacher 角色可查看/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /建立教師帳號/ }),
    ).not.toBeInTheDocument();
  });
});
