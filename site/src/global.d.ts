declare global {
  interface Window {
    React: any;
    ReactDOM: any;
  }

  namespace JSX {
    interface ElementChildrenAttribute {
      children: {};
    }

    interface IntrinsicElements {
      [elementName: string]: any;
    }
  }
}

export {};
