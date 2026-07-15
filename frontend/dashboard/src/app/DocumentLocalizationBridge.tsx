import { useLayoutEffect } from 'react';

import { useShellI18n } from './i18nContext';

const translatedAttributes = ['aria-description', 'aria-label', 'aria-valuetext', 'title', 'placeholder', 'alt'] as const;
const skippedElementNames = new Set(['CODE', 'KBD', 'PRE', 'SAMP', 'SCRIPT', 'STYLE', 'TEXTAREA']);

type TextTranslationRecord = { source: string; translated: string };
type AttributeTranslationRecord = { source: string; translated: string };

const textTranslations = new WeakMap<Text, TextTranslationRecord>();
const attributeTranslations = new WeakMap<Element, Map<string, AttributeTranslationRecord>>();

export function DocumentLocalizationBridge() {
  const i18n = useShellI18n();

  useLayoutEffect(() => {
    const root = document.querySelector<HTMLElement>('[data-dashboard-localization-root]');
    if (!root) return undefined;

    if (i18n.language !== 'zh-Hans') {
      restoreTree(root);
      document.title = 'Codex Usage Tracker React Dashboard';
      return undefined;
    }

    document.title = 'Codex Usage Tracker · 用量仪表盘';
    localizeTree(root, i18n.translateText);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData' && record.target instanceof Text) {
          localizeTextNode(record.target, i18n.translateText);
          continue;
        }
        if (record.type === 'attributes' && record.target instanceof Element) {
          localizeElementAttributes(record.target, i18n.translateText);
          continue;
        }
        for (const node of record.addedNodes) {
          if (node instanceof Text) {
            localizeTextNode(node, i18n.translateText);
          } else if (node instanceof Element) {
            localizeTree(node, i18n.translateText);
          }
        }
      }
    });
    observer.observe(root, {
      attributes: true,
      attributeFilter: [...translatedAttributes],
      characterData: true,
      childList: true,
      subtree: true,
    });
    return () => observer.disconnect();
  }, [i18n]);

  return null;
}

function localizeTree(root: Element, translate: (value: string) => string) {
  if (shouldSkipElement(root)) return;
  localizeElementAttributes(root, translate);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Element) {
      if (shouldSkipElement(node)) {
        node = nextNodeAfterSubtree(walker, node, root);
        continue;
      }
      localizeElementAttributes(node, translate);
    } else if (node instanceof Text) {
      localizeTextNode(node, translate);
    }
    node = walker.nextNode();
  }
}

function nextNodeAfterSubtree(walker: TreeWalker, element: Element, root: Element): Node | null {
  let current: Node | null = element;
  while (current && current !== root) {
    const sibling = walker.nextSibling();
    if (sibling) return sibling;
    current = current.parentNode;
    if (current) walker.currentNode = current;
  }
  return null;
}

function localizeTextNode(node: Text, translate: (value: string) => string) {
  const parent = node.parentElement;
  if (!parent || shouldSkipElement(parent)) return;
  const current = node.nodeValue ?? '';
  const previous = textTranslations.get(node);
  const source = previous && (current === previous.source || current === previous.translated)
    ? previous.source
    : current;
  const match = source.match(/^(\s*)([\s\S]*?)(\s*)$/u);
  if (!match || !match[2]) return;
  const translatedCore = translate(match[2]);
  const translated = `${match[1]}${translatedCore}${match[3]}`;
  textTranslations.set(node, { source, translated });
  if (translated !== current) node.nodeValue = translated;
}

function localizeElementAttributes(element: Element, translate: (value: string) => string) {
  if (shouldSkipElement(element)) return;
  const records = attributeTranslations.get(element) ?? new Map<string, AttributeTranslationRecord>();
  for (const attribute of translatedAttributes) {
    const current = element.getAttribute(attribute);
    if (!current) continue;
    const previous = records.get(attribute);
    const source = previous && (current === previous.source || current === previous.translated)
      ? previous.source
      : current;
    const translated = translate(source);
    records.set(attribute, { source, translated });
    if (translated !== current) element.setAttribute(attribute, translated);
  }
  if (records.size) attributeTranslations.set(element, records);
}

function restoreTree(root: Element) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  restoreElementAttributes(root);
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Text) {
      const record = textTranslations.get(node);
      if (record && node.nodeValue === record.translated) node.nodeValue = record.source;
    } else if (node instanceof Element) {
      restoreElementAttributes(node);
    }
    node = walker.nextNode();
  }
}

function restoreElementAttributes(element: Element) {
  const records = attributeTranslations.get(element);
  if (!records) return;
  for (const [attribute, record] of records) {
    if (element.getAttribute(attribute) === record.translated) {
      element.setAttribute(attribute, record.source);
    }
  }
}

function shouldSkipElement(element: Element): boolean {
  return skippedElementNames.has(element.tagName) || Boolean(element.closest('[data-localization-skip="true"]'));
}
