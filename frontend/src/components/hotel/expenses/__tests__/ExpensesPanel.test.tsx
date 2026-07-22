import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * EXPENSES-CLOSURE — standalone expenses section.
 * Covers permission-aware tabs (types needs manage_types), the create-button
 * gate (expenses.create), the multi-currency FX toggle (rate inputs appear ONLY
 * for a foreign currency), and submit-disabled-until-valid.
 */

const nav = vi.hoisted(() => ({ replace: vi.fn(), tab: "" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.tab ? `tab=${nav.tab}` : ""),
  usePathname: () => "/hotel/expenses",
  useRouter: () => ({
    replace: nav.replace, push: vi.fn(), back: vi.fn(),
    forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn(),
  }),
}));

const access = vi.hoisted(() => {
  let permissions = new Set<string>();
  let isManager = false;
  let loading = false;
  return {
    set(codes: string[], opts: { isManager?: boolean; loading?: boolean } = {}) {
      permissions = new Set(codes);
      isManager = opts.isManager ?? false;
      loading = opts.loading ?? false;
    },
    hook() {
      return {
        loading, isManager, permissions,
        can: (...codes: string[]) => isManager || codes.some((c) => permissions.has(c)),
        refresh: () => {},
      };
    },
  };
});
vi.mock("@/lib/session/HotelAccessContext", () => ({ useHotelAccess: () => access.hook() }));
vi.mock("@/lib/useQuickAction", () => ({ useQuickAction: () => {} }));

vi.mock("@/lib/api/expenses", () => ({
  listExpenses: vi.fn(),
  listExpenseTypes: vi.fn(),
  createExpense: vi.fn(),
  updateExpense: vi.fn(),
  voidExpense: vi.fn(),
  reverseExpense: vi.fn(),
  getExpenseVoucher: vi.fn(),
  createExpenseType: vi.fn(),
  updateExpenseType: vi.fn(),
  uploadExpenseAttachment: vi.fn(),
  deleteExpenseAttachment: vi.fn(),
  getExpenseAttachmentBlobUrl: vi.fn(),
  getExpenseMeta: vi.fn(),
  mintIdempotencyKey: () => "test-key",
}));

import { getExpenseMeta, listExpenses, listExpenseTypes } from "@/lib/api/expenses";
import type { Expense, ExpenseType, PaginatedResponse } from "@/lib/api/types";
import en from "@/lib/i18n/dictionaries/en.json";
import { ExpensesPanel } from "../ExpensesPanel";
import { ExpensesTab } from "../ExpensesTab";
import { renderWithProviders } from "@/test-utils";

const e = en.expenses;

function pageOf<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

const TYPE: ExpenseType = { id: 1, name: "Utilities", is_active: true, created_at: "", updated_at: "" };

beforeEach(() => {
  vi.clearAllMocks();
  nav.tab = "";
  (listExpenses as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(pageOf<Expense>([]));
  (listExpenseTypes as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([TYPE]);
  (getExpenseMeta as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    base_currency: "SAR",
    accepted_currencies: ["USD"],
  });
});

describe("ExpensesPanel — permission-aware tabs", () => {
  it("hides the Types tab without manage_types", async () => {
    access.set(["expenses.view"]);
    renderWithProviders(<ExpensesPanel />);
    await waitFor(() => expect(listExpenses).toHaveBeenCalled());
    expect(screen.queryByText(e.tabs.types)).not.toBeInTheDocument();
  });

  it("shows the Types tab with manage_types", async () => {
    access.set(["expenses.view", "expenses.manage_types"]);
    renderWithProviders(<ExpensesPanel />);
    await waitFor(() => expect(screen.getByText(e.tabs.types)).toBeInTheDocument());
  });
});

describe("ExpensesTab — create gate + FX", () => {
  it("hides Add expense without expenses.create", async () => {
    access.set(["expenses.view"]);
    renderWithProviders(<ExpensesTab />);
    await waitFor(() => expect(listExpenses).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: e.add })).not.toBeInTheDocument();
  });

  it("reveals FX inputs ONLY for a foreign currency", async () => {
    access.set(["expenses.view", "expenses.create"]);
    renderWithProviders(<ExpensesTab />);
    fireEvent.click((await screen.findAllByRole("button", { name: e.add }))[0]);
    const dialog = await screen.findByRole("dialog");
    // Base currency (SAR) → plain Amount, no FX inputs.
    await waitFor(() => expect(getExpenseMeta).toHaveBeenCalled());
    await within(dialog).findByLabelText(e.amount);
    expect(within(dialog).queryByLabelText(e.originalAmount)).not.toBeInTheDocument();
    // Switch to USD → FX inputs appear, plain Amount disappears.
    fireEvent.change(within(dialog).getByLabelText(e.currency), { target: { value: "USD" } });
    await within(dialog).findByLabelText(e.originalAmount);
    expect(within(dialog).getByLabelText(e.exchangeRate)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(e.amount)).not.toBeInTheDocument();
  });

  it("disables submit until required fields are valid", async () => {
    access.set(["expenses.view", "expenses.create"]);
    renderWithProviders(<ExpensesTab />);
    fireEvent.click((await screen.findAllByRole("button", { name: e.add }))[0]);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(getExpenseMeta).toHaveBeenCalled());
    const submit = within(dialog).getByRole("button", { name: e.submit });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(e.type), { target: { value: "1" } });
    fireEvent.change(within(dialog).getByLabelText(e.description), { target: { value: "Water" } });
    fireEvent.change(within(dialog).getByLabelText(e.amount), { target: { value: "50.00" } });
    await waitFor(() => expect(submit).not.toBeDisabled());
  });
});
