export type ZhHansPattern = {
  pattern: RegExp;
  replace: string | ((...matches: string[]) => string);
};
