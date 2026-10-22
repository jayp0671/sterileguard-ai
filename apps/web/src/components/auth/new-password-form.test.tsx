import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewPasswordForm } from "./new-password-form";

describe("NewPasswordForm", () => {
  it("keeps submit disabled for weak passwords and explains why", async () => {
    const onSubmit = vi.fn(async () => null);
    render(<NewPasswordForm submitLabel="Set password" onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("New password"), "short1");
    expect(screen.getByRole("button", { name: "Set password" })).toBeDisabled();
    expect(screen.getByText(/Needs 12\+ characters/)).toBeInTheDocument();
  });

  it("submits a strong, confirmed password", async () => {
    const onSubmit = vi.fn(async () => null);
    render(<NewPasswordForm submitLabel="Set password" onSubmit={onSubmit} />);
    const strong = "violet-kettle-orbit-91-canyon";
    await userEvent.type(screen.getByLabelText("New password"), strong);
    await userEvent.type(screen.getByLabelText("Confirm password"), strong);
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(onSubmit).toHaveBeenCalledWith(strong);
  });

  it("shows an error when the confirmation does not match", async () => {
    render(<NewPasswordForm submitLabel="Set password" onSubmit={vi.fn(async () => null)} />);
    await userEvent.type(screen.getByLabelText("New password"), "violet-kettle-orbit-91-canyon");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different-one-entirely-77");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
  });
});
