/**
 * @vitest-environment jsdom
 *
 * Component tests for ``<MentionPicker>`` — render contract, basic
 * keyboard nav, and the "click a file → onPick" wiring.
 *
 * Network is mocked out at the ``useWorkspaceBrowse`` level so we don't
 * couple test stability to React-Query internals.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Hoisted mock: the picker only consumes ``useWorkspaceBrowse`` from
// ``@/api/queries``. We stub the whole module (no ``importActual``) so
// the import chain doesn't try to resolve ``@taskforce/ui-shell`` — that
// workspace package needs a pre-built ``dist/`` which the dev container
// doesn't always have.
const useWorkspaceBrowseMock = vi.fn();

vi.mock("@/api/queries", () => ({
  useWorkspaceBrowse: (...args: unknown[]) => useWorkspaceBrowseMock(...args),
}));

// Re-declare the response shape locally so the test doesn't import it
// from the mocked module (which would pull in the rest of the file).
interface WorkspaceListResponse {
  root: string;
  path: string;
  entries: Array<{
    path: string;
    name: string;
    type: "file" | "dir";
    size?: number | null;
  }>;
  truncated: boolean;
}

import { MentionPicker } from "./MentionPicker";

function makeResponse(
  partial: Partial<WorkspaceListResponse> = {},
): WorkspaceListResponse {
  return {
    root: "/repo",
    path: "",
    entries: [],
    truncated: false,
    ...partial,
  };
}

function renderPicker(props: Partial<React.ComponentProps<typeof MentionPicker>>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MentionPicker
        open
        query=""
        onPick={vi.fn()}
        onDismiss={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("MentionPicker", () => {
  beforeEach(() => {
    useWorkspaceBrowseMock.mockReset();
  });

  afterEach(() => {
    // Cleanup any window-level listeners attached by the picker.
    document.body.innerHTML = "";
  });

  it("renders entries returned from the workspace browse query", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: makeResponse({
        entries: [
          { path: "src", name: "src", type: "dir", size: null },
          { path: "README.md", name: "README.md", type: "file", size: 120 },
        ],
      }),
      isLoading: false,
      isError: false,
    });

    renderPicker({});

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByText("src")).toBeInTheDocument();
    expect(screen.getByText("README.md")).toBeInTheDocument();
  });

  it("returns null markup when open is false", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: makeResponse(),
      isLoading: false,
      isError: false,
    });
    const { container } = renderPicker({ open: false });
    // Picker should render nothing while closed (so it can't steal
    // keyboard events).
    expect(container.firstChild).toBeNull();
  });

  it("shows a 'partial' badge when the backend reports truncation", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: makeResponse({
        entries: [
          { path: "f1", name: "f1", type: "file", size: 1 },
        ],
        truncated: true,
      }),
      isLoading: false,
      isError: false,
    });
    renderPicker({});
    expect(screen.getByText(/partial — type to narrow/i)).toBeInTheDocument();
  });

  it("calls onPick when a file is clicked (and not when a dir is clicked)", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: makeResponse({
        entries: [
          { path: "src", name: "src", type: "dir", size: null },
          { path: "README.md", name: "README.md", type: "file", size: 12 },
        ],
      }),
      isLoading: false,
      isError: false,
    });
    const onPick = vi.fn();
    renderPicker({ onPick });

    // Use mousedown to mirror what the picker listens to (matches the
    // production behaviour where mousedown precedes the textarea blur
    // that would otherwise close the picker first).
    fireEvent.mouseDown(screen.getByText("src"));
    expect(onPick).not.toHaveBeenCalled();

    fireEvent.mouseDown(screen.getByText("README.md"));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0].path).toBe("README.md");
  });

  it("dismisses on Escape", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: makeResponse({
        entries: [{ path: "a", name: "a", type: "file", size: 1 }],
      }),
      isLoading: false,
      isError: false,
    });
    const onDismiss = vi.fn();
    renderPicker({ onDismiss });

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("shows a loading state while the query is in flight", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    renderPicker({});
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders an error state if the query fails", () => {
    useWorkspaceBrowseMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });
    renderPicker({});
    expect(
      screen.getByText(/Failed to load workspace/i),
    ).toBeInTheDocument();
  });
});
