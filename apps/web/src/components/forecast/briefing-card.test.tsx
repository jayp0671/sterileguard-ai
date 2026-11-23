import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BriefingView } from "./briefing-card";

const base = {
  text: "Tomorrow's overtime is most likely 11.8 hours (range 10.9 to 12.5), a moderate burden day. Model estimate.",
  model: null,
  prompt_version: "v1",
  disclaimer: "Model estimate, not a guarantee.",
  ai_note: "An AI model rewrote the forecast numbers above into plain sentences.",
};

describe("BriefingView", () => {
  it("labels a template briefing as a plain summary", () => {
    render(<BriefingView briefing={{ ...base, source: "template" }} />);
    expect(screen.getByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText("Model estimate, not a guarantee.")).toBeInTheDocument();
  });

  it("labels an LLM briefing as AI-generated with an explanation", () => {
    render(
      <BriefingView briefing={{ ...base, source: "llm", model: "meta/llama-3.3-70b-instruct" }} />,
    );
    expect(screen.getByRole("heading", { name: "AI-generated summary" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What does the AI do here?" })).toBeInTheDocument();
  });
});
