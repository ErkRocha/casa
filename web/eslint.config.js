// ESLint do web (flat config): React + Vite + TypeScript.
//
// Só regras de correção — hooks, variáveis não usadas, tipos. Estilo
// (aspas, ponto e vírgula, quebra de linha) não é assunto do lint: nenhuma
// regra daqui briga com formatador. Os tipos de verdade quem checa é o
// `tsc --noEmit` do `npm run typecheck`.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Fast refresh do Vite: arquivo de componente que exporta outra coisa
      // perde o estado no hot reload. Aviso, não erro — não quebra build.
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // `_` no começo marca o não usado de propósito, como no tsconfig.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
);
