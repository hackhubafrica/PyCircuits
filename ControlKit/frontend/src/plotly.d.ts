declare module "plotly.js-dist-min" {
  const Plotly: {
    react: (el: HTMLElement, data: unknown[], layout?: unknown, config?: unknown) => Promise<void>;
    purge: (el: HTMLElement) => void;
  };
  export default Plotly;
}
