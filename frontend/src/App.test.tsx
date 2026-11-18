import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { saveSession } from "./api";
import type { Link } from "./types";
import {
  TEST_ANALYTICS,
  TEST_DASHBOARD,
  TEST_LINK,
  TEST_USER,
} from "./test/fixtures";

interface ApiCall {
  path: string;
  method: string;
  params: URLSearchParams;
  body: Record<string, unknown>;
  headers: Headers;
}

const json = (value: unknown, status = 200, headers?: HeadersInit) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

function mockApi(
  options: {
    links?: Link[];
    override?: (call: ApiCall) => Response | undefined;
  } = {},
) {
  let links = (options.links || [TEST_LINK]).map((link) => ({ ...link }));
  const calls: ApiCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const call: ApiCall = {
        path: url.pathname.replace(/^\/api\/v1/, ""),
        method: init?.method || "GET",
        params: url.searchParams,
        body: init?.body ? JSON.parse(String(init.body)) : {},
        headers: new Headers(init?.headers),
      };
      calls.push(call);
      const overridden = options.override?.(call);
      if (overridden) return overridden;
      if (call.path === "/auth/register") return json(TEST_USER, 201);
      if (call.path === "/auth/login")
        return json({
          access_token: "fixture-access-token",
          token_type: "bearer",
          expires_in: 1800,
          user: TEST_USER,
        });
      if (call.path === "/auth/me") return json(TEST_USER);
      if (call.path === "/dashboard")
        return json({
          ...TEST_DASHBOARD,
          total_links: links.length,
          active_links: links.filter((link) => link.is_active).length,
          top_links: links,
        });
      if (call.path.endsWith("/analytics"))
        return json({
          ...TEST_ANALYTICS,
          days: Number(call.params.get("days")),
        });
      if (call.path === "/urls" && call.method === "GET")
        return json({
          items: links,
          total: links.length,
          page: Number(call.params.get("page")),
          page_size: Number(call.params.get("page_size")),
        });
      if (call.path === "/urls" && call.method === "POST") {
        const created: Link = {
          ...TEST_LINK,
          id: "8c7fda21-d151-4601-a8ad-b6e460c6a4ca",
          original_url: String(call.body.original_url),
          title: String(call.body.title),
          short_code: String(call.body.custom_alias || "AbCd1234"),
          short_url: `http://localhost:8080/r/${call.body.custom_alias || "AbCd1234"}`,
          expires_at: (call.body.expires_at as string | null) || null,
          click_count: 0,
        };
        links = [created, ...links];
        return json(created, 201);
      }
      if (call.path.startsWith("/urls/") && call.method === "PATCH") {
        const id = call.path.split("/").at(-1);
        links = links.map((link) =>
          link.id === id ? ({ ...link, ...call.body } as Link) : link,
        );
        return json(links.find((link) => link.id === id));
      }
      if (call.path.startsWith("/urls/") && call.method === "DELETE") {
        links = links.filter((link) => link.id !== call.path.split("/").at(-1));
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected fixture request ${call.method} ${call.path}`);
    }),
  );
  return { calls };
}

function authenticated() {
  saveSession({
    access_token: "fixture-access-token",
    expires_at: Date.now() + 1_800_000,
    user: TEST_USER,
  });
}

async function enterCredentials(
  user: ReturnType<typeof userEvent.setup>,
  password = "A long test passphrase",
) {
  await user.type(screen.getByLabelText("Email address"), TEST_USER.email);
  await user.type(screen.getByLabelText(/^Password/), password);
}

async function awaitWorkspace() {
  await screen.findByRole("heading", { name: "Make every link count." });
  await screen.findByRole("table");
}

beforeEach(() => sessionStorage.clear());

describe("Account flows", () => {
  it("signs in and uses the returned bearer token for the actual dashboard response shape", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await enterCredentials(user);
    await user.click(
      screen.getByRole("button", { name: "Sign in to Linkforge" }),
    );
    await awaitWorkspace();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByText(TEST_LINK.title!),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Daily clicks, 5 total for the selected period",
      }),
    ).toBeInTheDocument();
    expect(
      api.calls
        .find((call) => call.path === "/dashboard")
        ?.headers.get("Authorization"),
    ).toBe("Bearer fixture-access-token");
    expect(
      JSON.parse(sessionStorage.getItem("linkforge.session.v1")!).user.email,
    ).toBe(TEST_USER.email);
  });

  it("registers with name/email/password, then signs in without inventing an account response", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("tab", { name: "Create account" }));
    await user.type(screen.getByLabelText("Your name"), TEST_USER.name);
    await enterCredentials(user);
    await user.click(
      screen.getByRole("button", { name: "Create your workspace" }),
    );
    await awaitWorkspace();
    const posts = api.calls.filter((call) => call.method === "POST");
    expect(posts.map((call) => call.path)).toEqual([
      "/auth/register",
      "/auth/login",
    ]);
    expect(posts[0].body).toEqual({
      name: TEST_USER.name,
      email: TEST_USER.email,
      password: "A long test passphrase",
    });
  });

  it("shows rejected credentials without logging in, then allows a successful retry", async () => {
    mockApi({
      override: (call) =>
        call.path === "/auth/login" && call.body.password === "incorrect"
          ? json({ detail: "Incorrect email or password" }, 401)
          : undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await enterCredentials(user, "incorrect");
    await user.click(
      screen.getByRole("button", { name: "Sign in to Linkforge" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Incorrect email or password",
    );
    expect(sessionStorage.getItem("linkforge.session.v1")).toBeNull();
    await user.clear(screen.getByLabelText(/^Password/));
    await user.type(
      screen.getByLabelText(/^Password/),
      "A long test passphrase",
    );
    await user.click(
      screen.getByRole("button", { name: "Sign in to Linkforge" }),
    );
    await awaitWorkspace();
  });

  it("keeps duplicate registration on the account form without calling login", async () => {
    const api = mockApi({
      override: (call) =>
        call.path === "/auth/register"
          ? json({ detail: "Email already registered" }, 409)
          : undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("tab", { name: "Create account" }));
    await user.type(screen.getByLabelText("Your name"), TEST_USER.name);
    await enterCredentials(user);
    await user.click(
      screen.getByRole("button", { name: "Create your workspace" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email already registered",
    );
    expect(api.calls.some((call) => call.path === "/auth/login")).toBe(false);
    expect(
      screen.getByRole("button", { name: "Create your workspace" }),
    ).toBeEnabled();
  });

  it("shows the server rate-limit retry interval", async () => {
    mockApi({
      override: (call) =>
        call.path === "/auth/login"
          ? json({ detail: "Too many attempts" }, 429, { "Retry-After": "60" })
          : undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await enterCredentials(user);
    await user.click(
      screen.getByRole("button", { name: "Sign in to Linkforge" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again in 60 seconds.",
    );
  });

  it("returns an invalid authenticated session to login and clears its stored token", async () => {
    authenticated();
    mockApi({
      override: (call) =>
        call.path === "/auth/me"
          ? json({ detail: "Token expired" }, 401)
          : undefined,
    });
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "Welcome back." }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("linkforge.session.v1")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(/sign in/i);
  });

  it("does not open an already-expired stored session", () => {
    saveSession({
      access_token: "expired-fixture",
      expires_at: Date.now() - 1,
      user: TEST_USER,
    });
    const api = mockApi();
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Welcome back." }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("linkforge.session.v1")).toBeNull();
    expect(api.calls).toHaveLength(0);
  });
});

describe("Link management", () => {
  beforeEach(authenticated);

  it("creates a custom link through the form and refreshes the real response into the table", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(screen.getByRole("button", { name: "Create link" }));
    const dialog = within(screen.getByRole("dialog"));
    await user.type(
      dialog.getByLabelText(/Destination URL/),
      "https://example.com/portfolio",
    );
    await user.type(dialog.getByLabelText(/Link title/), "My portfolio");
    await user.type(dialog.getByLabelText(/Custom short code/), "my-portfolio");
    await user.click(dialog.getByRole("button", { name: "Create link" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      await within(screen.getByRole("table")).findByText("My portfolio"),
    ).toBeInTheDocument();
    expect(
      api.calls.find((call) => call.method === "POST" && call.path === "/urls")
        ?.body,
    ).toEqual({
      original_url: "https://example.com/portfolio",
      title: "My portfolio",
      custom_alias: "my-portfolio",
      expires_at: null,
    });
  });

  it("preserves form values and displays a conflicting custom alias response", async () => {
    mockApi({
      override: (call) =>
        call.path === "/urls" && call.method === "POST"
          ? json({ detail: "This alias is already taken" }, 409)
          : undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(screen.getByRole("button", { name: "Create link" }));
    const dialog = within(screen.getByRole("dialog"));
    await user.type(
      dialog.getByLabelText(/Destination URL/),
      "https://example.com/portfolio",
    );
    await user.type(dialog.getByLabelText(/Custom short code/), "taken-code");
    await user.click(dialog.getByRole("button", { name: "Create link" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent(
      "This alias is already taken",
    );
    expect(dialog.getByLabelText(/Destination URL/)).toHaveValue(
      "https://example.com/portfolio",
    );
    expect(dialog.getByLabelText(/Custom short code/)).toHaveValue(
      "taken-code",
    );
    expect(dialog.getByRole("button", { name: "Create link" })).toBeEnabled();
  });

  it("edits an expired link without resubmitting its unchanged expiry, and permits explicitly clearing it", async () => {
    const api = mockApi({
      links: [{ ...TEST_LINK, expires_at: "2020-01-02T12:00:00Z" }],
    });
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(
      screen.getByRole("button", { name: "Edit Project notes" }),
    );
    let dialog = within(screen.getByRole("dialog"));
    expect(
      dialog.queryByLabelText(/Custom short code/),
    ).not.toBeInTheDocument();
    await user.clear(dialog.getByLabelText(/Link title/));
    await user.type(dialog.getByLabelText(/Link title/), "Updated notes");
    await user.click(dialog.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    let patches = api.calls.filter((call) => call.method === "PATCH");
    expect(patches[0].body).toEqual({
      original_url: TEST_LINK.original_url,
      title: "Updated notes",
    });
    await user.click(
      await screen.findByRole("button", { name: "Edit Updated notes" }),
    );
    dialog = within(screen.getByRole("dialog"));
    fireEvent.change(dialog.getByLabelText(/Expiration/), {
      target: { value: "" },
    });
    await user.click(dialog.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    patches = api.calls.filter((call) => call.method === "PATCH");
    expect(patches[1].body.expires_at).toBeNull();
  });

  it("sends debounced search and status parameters to the API", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.type(
      screen.getByRole("searchbox", { name: "Search links" }),
      "notes",
    );
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.path === "/urls" && call.params.get("search") === "notes",
        ),
      ).toBe(true),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Filter links by status" }),
      "inactive",
    );
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.path === "/urls" &&
            call.params.get("search") === "notes" &&
            call.params.get("status") === "inactive" &&
            call.params.get("page") === "1",
        ),
      ).toBe(true),
    );
  });

  it("pauses and resumes a link only after successful API updates", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(
      screen.getByRole("button", { name: "Pause Project notes" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Resume Project notes" }),
    );
    expect(
      await screen.findByRole("button", { name: "Pause Project notes" }),
    ).toBeEnabled();
    expect(
      api.calls
        .filter((call) => call.method === "PATCH")
        .map((call) => call.body),
    ).toEqual([{ is_active: false }, { is_active: true }]);
  });

  it("keeps a link active when a pause request fails and shows the server error", async () => {
    mockApi({
      override: (call) =>
        call.method === "PATCH"
          ? json({ detail: "Temporarily unable to update links" }, 503)
          : undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(
      screen.getByRole("button", { name: "Pause Project notes" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Temporarily unable to update links",
    );
    expect(
      screen.getByRole("button", { name: "Pause Project notes" }),
    ).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Resume Project notes" }),
    ).not.toBeInTheDocument();
  });

  it("requires delete confirmation and removes the row after the API returns 204", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(
      screen.getByRole("button", { name: "Delete Project notes" }),
    );
    expect(api.calls.some((call) => call.method === "DELETE")).toBe(false);
    await user.click(
      within(
        screen.getByRole("dialog", { name: "Delete this link?" }),
      ).getByRole("button", { name: "Delete link" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Your next good link starts here",
      }),
    ).toBeInTheDocument();
    expect(api.calls.find((call) => call.method === "DELETE")?.path).toBe(
      `/urls/${TEST_LINK.id}`,
    );
  });

  it("loads per-link analytics with referrer/device data and requests the selected period", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    await user.click(
      screen.getByRole("button", { name: "Analytics for Project notes" }),
    );
    const dialog = within(
      screen.getByRole("dialog", { name: "Project notes" }),
    );
    expect(await dialog.findByText("example.com")).toBeInTheDocument();
    expect(dialog.getByText("mobile")).toBeInTheDocument();
    expect(
      dialog.getByRole("img", {
        name: "Daily clicks, 5 total for the selected period",
      }),
    ).toBeInTheDocument();
    await user.selectOptions(
      dialog.getByRole("combobox", { name: "Analytics period" }),
      "7",
    );
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.path === `/urls/${TEST_LINK.id}/analytics` &&
            call.params.get("days") === "7",
        ),
      ).toBe(true),
    );
  });

  it("focuses the create dialog and restores focus when dismissed with Escape", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<App />);
    await awaitWorkspace();
    const trigger = screen.getByRole("button", { name: "Create link" });
    await user.click(trigger);
    await waitFor(() =>
      expect(
        within(screen.getByRole("dialog")).getByLabelText(/Destination URL/),
      ).toHaveFocus(),
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
