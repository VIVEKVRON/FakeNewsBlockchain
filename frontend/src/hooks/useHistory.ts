/**
 * frontend/src/hooks/useHistory.ts
 * Manages verification history stored in localStorage with JSON export support.
 */

import { useState, useEffect } from 'react';
import type { HistoryItem, TextVerificationResponse, ArticleVerificationResponse } from '@/types/verification';

const STORAGE_KEY = 'fakenews_verification_history_v1';

export function useHistory() {
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch (e) {
      console.error('Failed to write history to localStorage:', e);
    }
  }, [history]);

  const addClaimVerification = (res: TextVerificationResponse) => {
    const newItem: HistoryItem = {
      id: res.verification_id,
      type: 'claim',
      preview: res.claim,
      verdict: res.verdict,
      confidence: res.confidence_score,
      timestamp: res.created_at,
      data: res,
    };
    setHistory((prev) => [newItem, ...prev.filter((i) => i.id !== newItem.id)].slice(0, 50));
  };

  const addArticleVerification = (res: ArticleVerificationResponse) => {
    const newItem: HistoryItem = {
      id: res.article_id,
      type: 'article',
      title: res.title || 'Untitled Article',
      preview: res.summary_explanation,
      verdict: res.overall_verdict,
      confidence: res.overall_confidence,
      timestamp: res.created_at,
      data: res,
    };
    setHistory((prev) => [newItem, ...prev.filter((i) => i.id !== newItem.id)].slice(0, 50));
  };

  const clearHistory = () => {
    setHistory([]);
    localStorage.removeItem(STORAGE_KEY);
  };

  const removeHistoryItem = (id: string) => {
    setHistory((prev) => prev.filter((item) => item.id !== id));
  };

  const exportToJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(history, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `fakenews_verification_history_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return {
    history,
    addClaimVerification,
    addArticleVerification,
    clearHistory,
    removeHistoryItem,
    exportToJson,
  };
}
