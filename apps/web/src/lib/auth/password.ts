import { ZxcvbnFactory } from "@zxcvbn-ts/core";
import * as common from "@zxcvbn-ts/language-common";
import * as en from "@zxcvbn-ts/language-en";

/** Plan §9.1: at least 12 characters and a zxcvbn score of at least 3. */
export const MIN_PASSWORD_LENGTH = 12;
export const MIN_PASSWORD_SCORE = 3;

let factory: ZxcvbnFactory | null = null;
function scorer(): ZxcvbnFactory {
  factory ??= new ZxcvbnFactory({
    dictionary: { ...common.dictionary, ...en.dictionary },
    graphs: common.adjacencyGraphs,
    translations: en.translations,
  });
  return factory;
}

export type PasswordCheck = {
  score: 0 | 1 | 2 | 3 | 4;
  ok: boolean;
  tooShort: boolean;
  feedback: string[];
};

export function checkPassword(password: string, userInputs: string[] = []): PasswordCheck {
  const result = scorer().check(password, [...userInputs, "sterileguard", "sterile", "dental"]);
  const tooShort = password.length < MIN_PASSWORD_LENGTH;
  const feedback = [result.feedback.warning, ...result.feedback.suggestions].filter(
    (s): s is string => Boolean(s),
  );
  return {
    score: result.score,
    tooShort,
    ok: !tooShort && result.score >= MIN_PASSWORD_SCORE,
    feedback,
  };
}
