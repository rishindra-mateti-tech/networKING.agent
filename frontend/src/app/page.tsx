"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Users, User, Key, Settings, LogOut, Search, Plus, Star, Trash2,
  Send, RefreshCw, Check, Copy, Clipboard, FileText, ArrowRight, MessageSquare, AlertCircle,
  Zap, Loader2, Menu, X, BarChart3, ImagePlus, Sparkles, Mail, ExternalLink, ChevronDown, ChevronRight
} from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function Home() {
  // Authentication State
  const [token, setToken] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  // Global App State
  const [currentView, setCurrentView] = useState<"pipeline" | "twinagent" | "apikeys" | "settings" | "insights" | "uploads">("pipeline");
  const [connections, setConnections] = useState<any[]>([]);
  const [keys, setKeys] = useState<any[]>([]);
  const [settings, setSettings] = useState<any[]>([]);
  
  // Search & Filter
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // Modals / Selected Items
  const [selectedConnection, setSelectedConnection] = useState<any | null>(null);
  const [selectedVariant, setSelectedVariant] = useState<string>("referral");
  const [showAddModal, setShowAddModal] = useState(false);
  const [copiedText, setCopiedText] = useState(false);

  // Form Inputs: Add Connection
  const [newConnName, setNewConnName] = useState("");
  const [newConnTitle, setNewConnTitle] = useState("");
  const [newConnCompany, setNewConnCompany] = useState("");
  const [newConnLocation, setNewConnLocation] = useState("");
  const [newConnPosts, setNewConnPosts] = useState("");
  const [newConnUrl, setNewConnUrl] = useState("");
  const [connPdfFiles, setConnPdfFiles] = useState<File[]>([]);
  const [connScreenshotFile, setConnScreenshotFile] = useState<File | null>(null);
  const [connUploadLoading, setConnUploadLoading] = useState(false);
  const [customConnCount, setCustomConnCount] = useState<number | null>(null);
  const [customHiringStatus, setCustomHiringStatus] = useState<string>(""); // "" (auto), "ON" (yes), "OFF" (no)


  // Form Inputs: TwinAgent Settings
  const [targetRoles, setTargetRoles] = useState("");
  const [jobSearchStatus, setJobSearchStatus] = useState("");
  const [learningGoals, setLearningGoals] = useState("");
  const [toneExamples, setToneExamples] = useState("");
  const [latexCode, setLatexCode] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeUploadLoading, setResumeUploadLoading] = useState(false);
  const [settingsSaveLoading, setSettingsSaveLoading] = useState(false);

  // Form Inputs: API Keys
  const [newKeyVal, setNewKeyVal] = useState("");
  const [newKeyRole, setNewKeyRole] = useState<"primary" | "standby">("primary");
  const [newKeyLabel, setNewKeyLabel] = useState("");

  // Form Inputs: Telegram & Pacing Settings
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [pacingInterval, setPacingInterval] = useState("15");

  // Telegram test states
  const [telegramTestLoading, setTelegramTestLoading] = useState(false);
  const [telegramTestMessage, setTelegramTestMessage] = useState("");
  const [telegramTestError, setTelegramTestError] = useState("");

  // Slack integration state
  const [slackWebhookUrl, setSlackWebhookUrl] = useState("");
  const [slackTestLoading, setSlackTestLoading] = useState(false);
  const [slackTestMessage, setSlackTestMessage] = useState("");
  const [slackTestError, setSlackTestError] = useState("");

  // Interaction Log Chat Thread State
  const [threadLogs, setThreadLogs] = useState<any[]>([]);
  const [newLogMessage, setNewLogMessage] = useState("");
  const [logSender, setLogSender] = useState<"user" | "connection">("connection");
  const [intentInput, setIntentInput] = useState("");
  const [suggestedReply, setSuggestedReply] = useState("");
  const [isGeneratingReply, setIsGeneratingReply] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [queueStatus, setQueueStatus] = useState<{pending: number, processing: number, completed: number, failed: number, active_keys: number} | null>(null);
  const [intelTab, setIntelTab] = useState<"profile" | "company" | "strategy" | "personalization">("profile");

  // References
  const fileInputRef = useRef<HTMLInputElement>(null);
  const screenshotInputRef = useRef<HTMLInputElement>(null);
  const resumeInputRef = useRef<HTMLInputElement>(null);

  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // The three tabs that live inside the main workspace page
  const [homeTab, setHomeTab] = useState<"target" | "uploads" | "dashboard">("target");

  // Insights / Analytics
  const [analyticsData, setAnalyticsData] = useState<any | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [connCountRangeFilter, setConnCountRangeFilter] = useState<string>("all");
  const [seniorityFilter, setSeniorityFilter] = useState<string>("all");

  // Conversation screenshot upload
  const [screenshotUploadLoading, setScreenshotUploadLoading] = useState(false);
  const conversationScreenshotInputRef = useRef<HTMLInputElement>(null);

  // Ask-the-data analytics (available from every main page)
  const [analyticsQuestion, setAnalyticsQuestion] = useState("");
  const [analyticsAnswer, setAnalyticsAnswer] = useState("");
  const [analyticsAsking, setAnalyticsAsking] = useState(false);
  const [showAnalyticsPanel, setShowAnalyticsPanel] = useState(false);

  // Email drafting
  const [emailClientPreference, setEmailClientPreference] = useState("gmail");
  const [emailDraftLoadingId, setEmailDraftLoadingId] = useState<number | null>(null);
  const [expandedUploadRow, setExpandedUploadRow] = useState<number | null>(null);
  const [uploadsRowScreenshotLoadingId, setUploadsRowScreenshotLoadingId] = useState<number | null>(null);
  const uploadsScreenshotInputRef = useRef<HTMLInputElement>(null);
  const [uploadsScreenshotTargetId, setUploadsScreenshotTargetId] = useState<number | null>(null);

  // Fetch helper with Authorization header
  const fetchWithAuth = async (path: string, options: RequestInit = {}) => {
    const currentToken = token || localStorage.getItem("token");
    const headers = {
      ...(options.headers || {}),
      ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
    };
    try {
      const res = await fetch(`${BACKEND_URL}${path}`, { ...options, headers });
      setIsBackendOffline(false);
      return res;
    } catch (err) {
      setIsBackendOffline(true);
      throw err;
    }
  };

  // Load analytics whenever the Insights tab is opened
  useEffect(() => {
    if (currentView === "pipeline" && homeTab === "dashboard" && token) {
      fetchAnalytics();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentView, homeTab, token]);

  // On Mount: Check LocalStorage for token
  useEffect(() => {
    const localToken = localStorage.getItem("token");
    if (localToken) {
      setToken(localToken);
    }
  }, []);

  // Sync data when token updates
  useEffect(() => {
    if (token) {
      localStorage.setItem("token", token);
      loadAllData();
      
      // Auto-poll pipeline state every 5 seconds to track queue progress
      const interval = setInterval(() => {
        pollConnections();
      }, 5000);
      return () => clearInterval(interval);
    } else {
      localStorage.removeItem("token");
    }
  }, [token]);

  const loadAllData = async () => {
    await Promise.all([
      fetchConnections(),
      fetchApiKeys(),
      fetchSettings(),
      fetchQueueStatus()
    ]);
  };

  const fetchQueueStatus = async () => {
    try {
      const res = await fetchWithAuth("/api/orchestrator/status");
      if (res?.ok) {
        const data = await res.json();
        setQueueStatus(data);
      }
    } catch (e) {
      // Silently handle
    }
  };

  const triggerQueueNow = async () => {
    setIsTriggering(true);
    try {
      const res = await fetchWithAuth("/api/orchestrator/trigger", {
        method: "POST"
      });
      if (res?.ok) {
        // Refresh connections after a brief delay for processing to start
        setTimeout(() => {
          fetchConnections();
          fetchQueueStatus();
        }, 1500);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setTimeout(() => setIsTriggering(false), 2000);
    }
  };

  const fetchConnections = async () => {
    try {
      const res = await fetchWithAuth("/api/connections");
      if (res?.ok) {
        const data = await res.json();
        setConnections(data);
        // Sync selected connection details if open
        if (selectedConnection) {
          const updated = data.find((c: any) => c.id === selectedConnection.id);
          if (updated) setSelectedConnection(updated);
        }
      }
    } catch (e) {
      // Quietly set offline status handled in fetchWithAuth
    }
  };

  const fetchAnalytics = async () => {
    setAnalyticsLoading(true);
    try {
      const res = await fetchWithAuth("/api/analytics/overview");
      if (res?.ok) {
        const data = await res.json();
        setAnalyticsData(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const pollConnections = async () => {
    try {
      const res = await fetchWithAuth("/api/connections");
      if (res?.ok) {
        const data = await res.json();
        setConnections(data);
      }
    } catch (e) {
      // Quietly set offline status handled in fetchWithAuth
    }
  };

  const fetchApiKeys = async () => {
    try {
      const res = await fetchWithAuth("/api/keys");
      if (res.ok) {
        const data = await res.json();
        setKeys(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await fetchWithAuth("/api/settings");
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        
        // Map settings array to state variables
        const mapped: any = {};
        data.forEach((s: any) => { mapped[s.key] = s.value; });
        
        setTargetRoles(mapped["target_roles"] || "");
        setJobSearchStatus(mapped["job_search_status"] || "");
        setLearningGoals(mapped["learning_goals"] || "");
        setToneExamples(mapped["tone_examples"] || "");
        setLatexCode(mapped["resume_latex"] || "");
        setTelegramToken(mapped["telegram_token"] || "");
        setTelegramChatId(mapped["telegram_chat_id"] || "");
        setSlackWebhookUrl(mapped["slack_webhook_url"] || "");
        setEmailClientPreference(mapped["email_client_preference"] || "gmail");
        setPacingInterval(mapped["pacing_interval_minutes"] || "15");
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Auth Operations
  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    const path = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
    const payload = authMode === "login" 
      ? { email, password } 
      : { email, password };
      
    try {
      const res = await fetch(`${BACKEND_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      if (!res.ok) {
        setAuthError(data.detail || "Authentication failed");
        return;
      }
      
      if (authMode === "login") {
        setToken(data.access_token);
      } else {
        // Registered successfully, auto login
        setAuthMode("login");
        const loginRes = await fetch(`${BACKEND_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        const loginData = await loginRes.json();
        if (loginRes.ok) {
          setToken(loginData.access_token);
        }
      }
    } catch (err) {
      setAuthError("Failed to connect to backend");
    }
  };

  const handleLogout = () => {
    setToken(null);
    localStorage.removeItem("token");
    setConnections([]);
    setKeys([]);
    setSettings([]);
    setSelectedConnection(null);
  };

  // Settings Save
  const handleSaveSettings = async () => {
    setSettingsSaveLoading(true);
    const batch = {
      settings: [
        { key: "target_roles", value: targetRoles },
        { key: "job_search_status", value: jobSearchStatus },
        { key: "learning_goals", value: learningGoals },
        { key: "tone_examples", value: toneExamples },
        { key: "resume_latex", value: latexCode },
        { key: "telegram_token", value: telegramToken },
        { key: "telegram_chat_id", value: telegramChatId },
        { key: "slack_webhook_url", value: slackWebhookUrl },
        { key: "email_client_preference", value: emailClientPreference },
        { key: "pacing_interval_minutes", value: pacingInterval }
      ]
    };
    
    try {
      const res = await fetchWithAuth("/api/settings/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(batch)
      });
      if (res.ok) {
        alert("TwinAgent configuration saved successfully!");
        fetchSettings();
      }
    } catch (e) {
      alert("Failed to save settings");
    } finally {
      setSettingsSaveLoading(false);
    }
  };

  // Resume PDF Upload
  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setResumeUploadLoading(true);
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetchWithAuth("/api/settings/upload-resume", {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        alert("Resume PDF uploaded and parsed successfully!");
        fetchSettings();
      } else {
        const d = await res.json();
        alert(d.detail || "Upload failed");
      }
    } catch (err) {
      alert("Failed to upload resume");
    } finally {
      setResumeUploadLoading(false);
      setResumeFile(null);
    }
  };

  // API Key operations
  const handleAddApiKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyVal) return;
    
    try {
      const res = await fetchWithAuth("/api/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key_value: newKeyVal,
          role: newKeyRole,
          label: newKeyLabel
        })
      });
      if (res.ok) {
        setNewKeyVal("");
        setNewKeyLabel("");
        fetchApiKeys();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggleKey = async (keyId: number) => {
    try {
      const res = await fetchWithAuth(`/api/keys/${keyId}/toggle`, {
        method: "PUT"
      });
      if (res.ok) fetchApiKeys();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteKey = async (keyId: number) => {
    if (!confirm("Are you sure you want to remove this API key?")) return;
    try {
      const res = await fetchWithAuth(`/api/keys/${keyId}`, {
        method: "DELETE"
      });
      if (res.ok) fetchApiKeys();
    } catch (e) {
      console.error(e);
    }
  };

  const handleTestTelegram = async () => {
    setTelegramTestLoading(true);
    setTelegramTestMessage("");
    setTelegramTestError("");
    try {
      const res = await fetchWithAuth("/api/settings/test-telegram", {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        setTelegramTestMessage(data.message || "Test alert sent!");
      } else {
        setTelegramTestError(data.detail || "Failed to send test alert.");
      }
    } catch (err: any) {
      setTelegramTestError(err.message || "Network error.");
    } finally {
      setTelegramTestLoading(false);
    }
  };

  const handleTestSlack = async () => {
    setSlackTestLoading(true);
    setSlackTestMessage("");
    setSlackTestError("");
    try {
      const res = await fetchWithAuth("/api/settings/test-slack", {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        setSlackTestMessage(data.message || "Test alert sent!");
      } else {
        setSlackTestError(data.detail || "Failed to send test alert.");
      }
    } catch (err: any) {
      setSlackTestError(err.message || "Network error.");
    } finally {
      setSlackTestLoading(false);
    }
  };

  // Connection operations
  const handleAddConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnUploadLoading(true);
    
    try {
      if (connPdfFiles.length > 0 || connScreenshotFile || newConnUrl) {
        // Multi-part creation (PDF/Screenshot/URL)
        if (connPdfFiles.length > 0) {
          for (const file of connPdfFiles) {
            const formData = new FormData();
            formData.append("file", file);
            if (connScreenshotFile) formData.append("screenshot", connScreenshotFile);
            if (newConnUrl) formData.append("profile_url", newConnUrl);
            if (newConnName) formData.append("name", newConnName);
            if (newConnTitle) formData.append("current_title", newConnTitle);
            if (newConnCompany) formData.append("company", newConnCompany);
            if (newConnLocation) formData.append("location", newConnLocation);
            if (newConnPosts) formData.append("posts", newConnPosts);
            if (customConnCount !== null) formData.append("connection_count", String(customConnCount));
            if (customHiringStatus) formData.append("hiring_badge_status", customHiringStatus);

            const res = await fetchWithAuth("/api/connections/upload-profile", {
              method: "POST",
              body: formData
            });
            if (!res.ok) {
              const d = await res.json();
              console.error("Failed to process file:", file.name, d.detail);
            }
          }
        } else {
          const formData = new FormData();
          if (connScreenshotFile) formData.append("screenshot", connScreenshotFile);
          if (newConnUrl) formData.append("profile_url", newConnUrl);
          if (newConnName) formData.append("name", newConnName);
          if (newConnTitle) formData.append("current_title", newConnTitle);
          if (newConnCompany) formData.append("company", newConnCompany);
          if (newConnLocation) formData.append("location", newConnLocation);
          if (newConnPosts) formData.append("posts", newConnPosts);
          if (customConnCount !== null) formData.append("connection_count", String(customConnCount));
          if (customHiringStatus) formData.append("hiring_badge_status", customHiringStatus);

          const res = await fetchWithAuth("/api/connections/upload-profile", {
            method: "POST",
            body: formData
          });
          if (!res.ok) {
            const d = await res.json();
            alert(d.detail || "Failed to process target details");
            setConnUploadLoading(false);
            return;
          }
        }

        setShowAddModal(false);
        setConnPdfFiles([]);
        setConnScreenshotFile(null);
        setNewConnUrl("");
        setNewConnName("");
        setNewConnTitle("");
        setNewConnCompany("");
        setNewConnLocation("");
        setNewConnPosts("");
        setCustomConnCount(null);
        setCustomHiringStatus("");
        fetchConnections();
      } else {
        // Manual JSON creation
        const payload = {
          name: newConnName,
          current_title: newConnTitle,
          company: newConnCompany,
          location: newConnLocation,
          posts_text: newConnPosts,
          profile_url: newConnUrl || null,
          connection_count: customConnCount || 0
        };
        const res = await fetchWithAuth("/api/connections", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          setShowAddModal(false);
          setNewConnName("");
          setNewConnTitle("");
          setNewConnCompany("");
          setNewConnLocation("");
          setNewConnPosts("");
          setNewConnUrl("");
          setCustomConnCount(null);
          setCustomHiringStatus("");
          fetchConnections();
        } else {
          const d = await res.json();
          alert(d.detail || "Failed to create target manually");
        }
      }
    } catch (err) {
      alert("Failed to add connection");
    } finally {
      setConnUploadLoading(false);
    }
  };


  const handleToggleStar = async (connId: number) => {
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}/star`, {
        method: "PUT"
      });
      if (res.ok) fetchConnections();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteConnection = async (connId: number) => {
    if (!confirm("Remove this connection?")) return;
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        fetchConnections();
        if (selectedConnection?.id === connId) {
          setSelectedConnection(null);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleUpdateStatus = async (connId: number, nextStatus: string) => {
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus })
      });
      if (res.ok) fetchConnections();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectVariant = async (connId: number, variant: string) => {
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}/select-variant?variant=${variant}`, {
        method: "PUT"
      });
      if (res.ok) {
        fetchConnections();
        setSelectedVariant(variant as any);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Follow-up thread logs
  const fetchThreadLogs = async (connId: number) => {
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}/logs`);
      if (res.ok) {
        const data = await res.json();
        setThreadLogs(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddThreadLog = async () => {
    if (!newLogMessage || !selectedConnection) return;
    try {
      const res = await fetchWithAuth(`/api/connections/${selectedConnection.id}/logs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: newLogMessage,
          sender: logSender
        })
      });
      if (res.ok) {
        setNewLogMessage("");
        fetchThreadLogs(selectedConnection.id);
        fetchConnections(); // Refresh status on dashboard
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleUploadConversationScreenshot = async (file: File) => {
    if (!selectedConnection) return;
    setScreenshotUploadLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetchWithAuth(`/api/connections/${selectedConnection.id}/logs/upload-screenshot`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        fetchThreadLogs(selectedConnection.id);
        fetchConnections();
      } else {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || "Failed to analyze screenshot. Make sure you have an active API key configured.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setScreenshotUploadLoading(false);
    }
  };

  const handleAskAnalytics = async () => {
    if (!analyticsQuestion.trim()) return;
    setAnalyticsAsking(true);
    setAnalyticsAnswer("");
    try {
      const res = await fetchWithAuth("/api/analytics/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: analyticsQuestion })
      });
      const data = await res.json();
      setAnalyticsAnswer(res.ok ? data.answer : (data.detail || "Failed to analyze."));
    } catch (e: any) {
      setAnalyticsAnswer(e.message || "Network error.");
    } finally {
      setAnalyticsAsking(false);
    }
  };

  const handleGenerateEmail = async (connId: number) => {
    setEmailDraftLoadingId(connId);
    try {
      const res = await fetchWithAuth(`/api/connections/${connId}/generate-email`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        fetchConnections();
        setExpandedUploadRow(connId);
      } else {
        alert(data.detail || "Failed to generate email.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setEmailDraftLoadingId(null);
    }
  };

  // Hands the finished draft off to whichever mail client the user prefers, with
  // the recipient, subject and body pre-filled so it opens as a reviewable draft
  // rather than anything being sent automatically.
  const openEmailClient = (conn: any) => {
    const to = encodeURIComponent(conn.candidate_email || "");
    const subject = encodeURIComponent(conn.generated_email_subject || "");
    const body = encodeURIComponent(conn.generated_email_body || "");
    let url = "";
    if (emailClientPreference === "gmail") {
      url = `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${subject}&body=${body}`;
    } else if (emailClientPreference === "outlook") {
      url = `https://outlook.office.com/mail/deeplink/compose?to=${to}&subject=${subject}&body=${body}`;
    } else {
      url = `mailto:${conn.candidate_email || ""}?subject=${subject}&body=${body}`;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const handleUploadScreenshotForRow = async (connId: number, file: File) => {
    setUploadsRowScreenshotLoadingId(connId);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetchWithAuth(`/api/connections/${connId}/logs/upload-screenshot`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        fetchConnections();
        if (selectedConnection?.id === connId) fetchThreadLogs(connId);
      } else {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || "Failed to analyze screenshot.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setUploadsRowScreenshotLoadingId(null);
    }
  };

  const handleGenerateReply = async () => {
    if (!selectedConnection) return;
    setIsGeneratingReply(true);
    setSuggestedReply("");
    try {
      const res = await fetchWithAuth(
        `/api/connections/${selectedConnection.id}/generate-reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_intent: intentInput || null
          })
        }
      );
      if (res.ok) {
        const d = await res.json();
        setSuggestedReply(d.suggested_reply);
      } else {
        alert("Failed to generate follow-up. Make sure you have configured active API keys.");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingReply(false);
    }
  };

  const handleCopyClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  // Load thread history when card detail opens
  useEffect(() => {
    if (selectedConnection) {
      fetchThreadLogs(selectedConnection.id);
      setSelectedVariant(selectedConnection.selected_variant || "referral");
      setSuggestedReply("");
      setIntentInput("");
    }
  }, [selectedConnection]);

  // Kanban Pipeline Columns mapping
  const columns = [
    // One consistent surface for every column. Status is signalled by the small
    // count pill and the card contents, not by giving each column its own border
    // colour, which read as noisy and unconsidered.
    { title: "Pending", statusKeys: ["pending", "failed"], color: "border-white/10 bg-white/[0.02]" },
    { title: "Processing", statusKeys: ["processing"], color: "border-white/10 bg-white/[0.02]" },
    { title: "Draft Ready", statusKeys: ["completed"], color: "border-white/10 bg-white/[0.02]" },
    { title: "Sent", statusKeys: ["sent"], color: "border-white/10 bg-white/[0.02]" },
    { title: "Replied / Chatting", statusKeys: ["replied", "follow_up"], color: "border-white/10 bg-white/[0.02]" },
    { title: "Funnel Closed", statusKeys: ["interview", "closed"], color: "border-white/10 bg-white/[0.02]" }
  ];

  // Filtering connections list
  const filteredConnections = connections.filter(conn => {
    const matchesSearch = searchQuery === "" || 
      conn.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (conn.company && conn.company.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (conn.current_title && conn.current_title.toLowerCase().includes(searchQuery.toLowerCase()));
      
    const matchesStatus = statusFilter === "" || conn.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // Calculate active Worker threads count
  const activeWorkersCount = keys.filter(k => k.is_active && k.role === "primary" && (!k.cooldown_until || new Date(k.cooldown_until) < new Date())).length;

  if (!token) {
    // --- AUTHENTICATION ENTRY PANEL ---
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col justify-center items-center px-4">
        <div className="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-2xl p-8 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-zinc-700 to-zinc-500"></div>
          <div className="text-center mb-8">
            <img src="/icon-192.png" alt="networKING.agent" className="w-16 h-16 mx-auto mb-3" />
            <h1 className="text-3xl font-extrabold tracking-tight text-[#ebe5d6]">
              networ<span className="text-[#4d8565]">KING</span>.agent
            </h1>
            <p className="text-sm text-zinc-400 mt-2">
              Relationship-first LinkedIn outreach automation
            </p>
          </div>

          <form onSubmit={handleAuthSubmit} className="space-y-6">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Email Address</label>
              <input 
                type="email" 
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Password</label>
              <input 
                type="password" 
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                placeholder="••••••••"
              />
            </div>

            {authError && (
              <div className="flex items-center space-x-2 text-xs text-rose-500 bg-rose-500/10 border border-rose-500/20 rounded-lg p-3">
                <AlertCircle size={16} />
                <span>{authError}</span>
              </div>
            )}

            <button 
              type="submit"
              className="w-full bg-zinc-900 border border-zinc-800 text-zinc-300 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 text-sm font-semibold py-3 rounded-lg transition-colors cursor-pointer shadow-lg shadow-zinc-950/40"
            >
              {authMode === "login" ? "Sign In" : "Create Account"}
            </button>

          </form>

          <div className="text-center mt-6">
            <button 
              onClick={() => {
                setAuthMode(authMode === "login" ? "register" : "login");
                setAuthError("");
              }}
              className="text-xs text-zinc-400 hover:text-zinc-200 underline transition-colors cursor-pointer"
            >
              {authMode === "login" ? "Need an account? Sign up" : "Already have an account? Log in"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- SAAS DASHBOARD INTERFACE ---
  const goToView = (view: "pipeline" | "twinagent" | "apikeys" | "settings" | "insights" | "uploads") => {
    setCurrentView(view);
    setSelectedConnection(null);
    setMobileNavOpen(false);
  };

  // Shared across the three main pages. Lets the user interrogate their own
  // outreach data in plain language, answered by their own Gemini keys.
  const renderAnalyticsPanel = () => (
    <div className="bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-xl overflow-hidden">
      <button
        onClick={() => setShowAnalyticsPanel(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 text-xs font-bold text-white uppercase tracking-wider">
          <Sparkles size={14} className="text-[#4d8565]" />
          View Analytics
        </span>
        <span className="text-[10px] text-zinc-500 font-mono">{showAnalyticsPanel ? "hide" : "ask anything"}</span>
      </button>

      {showAnalyticsPanel && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
          <p className="text-[10px] text-zinc-500">
            Ask about your own outreach in plain language. Runs on your configured Gemini keys.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {[
              "Which type of person replies to me most?",
              "Who should I follow up with first?",
              "Why is my reply rate low?",
              "Which companies ignored me?",
            ].map(q => (
              <button
                key={q}
                onClick={() => setAnalyticsQuestion(q)}
                className="text-[10px] bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-400 hover:text-white px-2 py-1 rounded-full transition-colors cursor-pointer"
              >
                {q}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={analyticsQuestion}
              onChange={e => setAnalyticsQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleAskAnalytics(); }}
              placeholder="e.g. which seniority level actually replies to me?"
              className="flex-1 bg-zinc-950/60 border border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-white/20"
            />
            <button
              onClick={handleAskAnalytics}
              disabled={analyticsAsking || !analyticsQuestion.trim()}
              className="bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white px-4 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer disabled:opacity-40 shrink-0"
            >
              {analyticsAsking ? <Loader2 size={13} className="animate-spin" /> : "Ask"}
            </button>
          </div>
          {analyticsAnswer && (
            <div className="bg-zinc-950/60 border border-white/10 rounded-lg p-3 text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap">
              {analyticsAnswer}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200 flex">
      {/* Mobile nav backdrop */}
      {mobileNavOpen && (
        <div
          onClick={() => setMobileNavOpen(false)}
          className="fixed inset-0 bg-black/60 z-30 lg:hidden"
        />
      )}

      {/* 1. SIDEBAR (off-canvas drawer on mobile/tablet, static column at lg+) */}
      <aside className={`fixed lg:static inset-y-0 left-0 w-64 border-r border-zinc-800 bg-zinc-900 lg:bg-zinc-900/50 flex flex-col z-40 shrink-0 transform transition-transform duration-200 ${
        mobileNavOpen ? "translate-x-0" : "-translate-x-full"
      } lg:translate-x-0`}>
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <img src="/icon-192.png" alt="networKING.agent" className="w-9 h-9 rounded-lg shadow-md shadow-zinc-950/40" />
            <div>
              <h1 className="text-base font-extrabold tracking-tight text-[#ebe5d6]">
                networ<span className="text-[#4d8565]">KING</span>.agent
              </h1>
              <p className="text-[10px] text-zinc-500 font-mono">v1.0.0 SaaS Edition</p>
            </div>
          </div>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="lg:hidden p-1 text-zinc-500 hover:text-white cursor-pointer"
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          <button
            onClick={() => goToView("pipeline")}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              currentView === "pipeline" ? "bg-zinc-800 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            }`}
          >
            <Users size={18} />
            <span>Outreach Pipeline</span>
          </button>

          <div className="pt-4 mt-2 border-t border-white/5">
            <span className="px-4 text-[9px] font-semibold text-zinc-600 uppercase tracking-wider">Configuration</span>
          </div>

          <button
            onClick={() => goToView("twinagent")}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              currentView === "twinagent" ? "bg-zinc-800 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            }`}
          >
            <User size={18} />
            <span>TwinAgent Profile</span>
          </button>
          <button
            onClick={() => goToView("apikeys")}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              currentView === "apikeys" ? "bg-zinc-800 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            }`}
          >
            <Key size={18} />
            <div className="flex-1 flex items-center justify-between">
              <span>API Key Workers</span>
              {activeWorkersCount > 0 && (
                <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded-full font-mono font-semibold animate-pulse">
                  {activeWorkersCount} Active
                </span>
              )}
            </div>
          </button>
          <button
            onClick={() => goToView("settings")}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              currentView === "settings" ? "bg-zinc-800 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            }`}
          >
            <Settings size={18} />
            <span>Notifications & Pacing</span>
          </button>
        </nav>

        <div className="p-4 border-t border-zinc-800">
          <button
            onClick={handleLogout}
            className="w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-sm font-medium text-zinc-400 hover:bg-rose-950/20 hover:text-rose-400 transition-colors cursor-pointer"
          >
            <LogOut size={18} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* 2. MAIN WORKSPACE CONTENT */}
      <main className="flex-1 min-w-0 flex flex-col overflow-y-auto relative bg-zinc-950">
        {/* Mobile/tablet top bar (sidebar is off-canvas below the lg breakpoint) */}
        <div className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 sticky top-0 z-20">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="p-2 -ml-2 text-zinc-300 hover:text-white cursor-pointer"
            aria-label="Open menu"
          >
            <Menu size={20} />
          </button>
          <h1 className="text-sm font-bold text-[#ebe5d6] flex items-center gap-2">
            <img src="/icon-192.png" alt="networKING.agent" className="w-6 h-6 rounded-md" />
            networ<span className="text-[#4d8565]">KING</span>.agent
          </h1>
          <div className="w-9" />
        </div>

        {isBackendOffline && (
          <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2.5 text-xs text-amber-400 text-center flex items-center justify-center space-x-2 font-medium shrink-0">
            <AlertCircle size={14} className="shrink-0" />
            <span>Backend server unreachable ({BACKEND_URL}). Run <code className="bg-amber-950/40 px-1.5 py-0.5 rounded font-mono text-amber-300">python run.py</code> to start the FastAPI server.</span>
          </div>
        )}
        
        {/* The three main tabs live inside this page, not in the sidebar */}
        {currentView === "pipeline" && (
          <div className="px-6 pt-5 pb-1 shrink-0">
            <div className="inline-flex items-center gap-1 bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-xl p-1">
              {([
                { id: "target", label: "Outreach Target", icon: <Users size={14} /> },
                { id: "uploads", label: "Uploads", icon: <FileText size={14} />, count: connections.length },
                { id: "dashboard", label: "Dashboard", icon: <BarChart3 size={14} /> },
              ] as const).map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setHomeTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                    homeTab === tab.id
                      ? "bg-white/10 text-white"
                      : "text-zinc-500 hover:text-zinc-200"
                  }`}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                  {"count" in tab && tab.count > 0 && (
                    <span className="text-[9px] bg-white/10 text-zinc-400 px-1.5 py-0.5 rounded-full font-mono">
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* TAB 1: OUTREACH TARGET (kanban + add profiles) */}
        {currentView === "pipeline" && homeTab === "target" && (
          <div className="flex-1 flex flex-col">

            {/* Top Command Bar */}
            <div className="p-6 border-b border-zinc-800 bg-zinc-900/10 flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center space-x-4 flex-1 max-w-lg">
                <div className="relative flex-1">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                  <input 
                    type="text"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    placeholder="Search name, title, or company..."
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                  />
                </div>
              </div>
              <div className="flex items-center space-x-3">
                {/* Queue Status Indicator */}
                {queueStatus && (queueStatus.pending > 0 || queueStatus.processing > 0) && (
                  <div className="flex items-center space-x-2 text-[10px] font-mono">
                    {queueStatus.pending > 0 && (
                      <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-1 rounded-md">
                        {queueStatus.pending} pending
                      </span>
                    )}
                    {queueStatus.processing > 0 && (
                      <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-1 rounded-md animate-pulse">
                        {queueStatus.processing} processing
                      </span>
                    )}
                  </div>
                )}
                <button 
                  onClick={triggerQueueNow}
                  disabled={isTriggering}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-semibold transition-all cursor-pointer border ${
                    isTriggering 
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" 
                      : "bg-zinc-900/40 text-zinc-300 border-zinc-700 hover:border-emerald-500/50 hover:text-emerald-400 hover:bg-emerald-950/20"
                  }`}
                  title="Instantly wake up workers to process pending queue"
                >
                  {isTriggering ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Zap size={14} />
                  )}
                  <span>{isTriggering ? "Triggered!" : "Process Queue Now"}</span>
                </button>
                <button 
                  onClick={loadAllData}
                  className="p-2 border border-zinc-800 hover:border-zinc-700 bg-zinc-900/40 rounded-lg text-zinc-400 hover:text-white transition-colors cursor-pointer"
                  title="Refresh Queue"
                >
                  <RefreshCw size={16} />
                </button>
                <button 
                  onClick={() => setShowAddModal(true)}
                  className="bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 hover:border-zinc-700 text-sm font-semibold text-zinc-300 hover:text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition-colors cursor-pointer shadow-md"
                >
                  <Plus size={16} />
                  <span>Add Outreach Target</span>
                </button>
              </div>
            </div>

            {/* Kanban columns content */}
            <div className="px-6 pt-4">
              {renderAnalyticsPanel()}
            </div>

            <div className="flex-1 p-6 overflow-x-auto flex gap-6 items-start">
              {columns.map(col => {
                const colConnections = filteredConnections.filter(c => col.statusKeys.includes(c.status));
                return (
                  <div key={col.title} className="w-80 shrink-0 flex flex-col max-h-full">
                    
                    {/* Column Header */}
                    <div className="flex items-center justify-between mb-4 px-2">
                      <div className="flex items-center space-x-2">
                        <h2 className="text-sm font-bold text-zinc-200">{col.title}</h2>
                        <span className="text-[10px] bg-zinc-800 text-zinc-400 border border-zinc-700 px-1.5 py-0.5 rounded-full font-mono">
                          {colConnections.length}
                        </span>
                      </div>
                    </div>

                    {/* Column Items area */}
                    <div className={`flex-1 overflow-y-auto space-y-3 rounded-xl border p-3 min-h-[120px] max-h-[70vh] transition-colors ${col.color}`}>
                      {colConnections.map(conn => (
                        <div 
                          key={conn.id}
                          onClick={() => setSelectedConnection(conn)}
                          className="bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl p-4 cursor-pointer hover:shadow-lg transition-all group relative"
                        >
                          <div className="flex justify-between items-start mb-2">
                            <h3 className="text-sm font-bold text-white group-hover:text-zinc-300 transition-colors pr-6">
                              {conn.name}
                            </h3>
                            <div className="flex items-center space-x-1 absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button 
                                onClick={(e) => { e.stopPropagation(); handleToggleStar(conn.id); }}
                                className={`p-1 rounded hover:bg-zinc-800 transition-colors ${conn.is_starred ? "text-amber-400" : "text-zinc-500"}`}
                              >
                                <Star size={14} fill={conn.is_starred ? "currentColor" : "none"} />
                              </button>
                              <button 
                                onClick={(e) => { e.stopPropagation(); handleDeleteConnection(conn.id); }}
                                className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-rose-400 transition-colors"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                            {!conn.is_starred && conn.is_starred !== undefined && (
                              <div className="absolute top-4 right-4 text-amber-500 w-1.5 h-1.5 rounded-full bg-amber-500 hidden" />
                            )}
                            {conn.is_starred && (
                              <Star size={12} className="text-amber-400 absolute top-4 right-4" fill="currentColor" />
                            )}
                          </div>
                          
                          <p className="text-xs text-zinc-400 line-clamp-1">{conn.current_title || "No Title"}</p>
                          <p className="text-[10px] text-zinc-500 font-medium mt-1">{conn.company || "No Company"}</p>

                          {/* Quick Bridge Score tags */}
                          {conn.best_angle && (
                            <div className="mt-3 pt-3 border-t border-zinc-800/80 flex flex-wrap items-center gap-1.5">
                              <span className="text-[9px] font-semibold uppercase tracking-wider bg-zinc-900 text-zinc-400 border border-zinc-800 px-1.5 py-0.5 rounded">
                                {conn.best_angle}
                              </span>
                              {conn.years_experience > 0 && (
                                <span className="text-[9px] font-mono bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                                  {conn.years_experience} yrs exp
                                </span>
                              )}
                            </div>
                          )}

                          {/* Connection logs state indicator */}
                          {conn.error_message && (
                            <div className="mt-2 text-[9px] text-rose-400 bg-rose-950/20 border border-rose-900/30 rounded p-1.5 flex items-center space-x-1">
                              <AlertCircle size={10} className="shrink-0" />
                              <span className="line-clamp-1">{conn.error_message}</span>
                            </div>
                          )}
                        </div>
                      ))}

                      {colConnections.length === 0 && (
                        <div className="h-24 flex items-center justify-center border border-dashed border-zinc-800 rounded-lg text-[10px] text-zinc-600 font-mono">
                          Column empty
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* VIEW F: UPLOADS TABLE */}
        {currentView === "pipeline" && homeTab === "uploads" && (
          <div className="p-4 sm:p-6 w-full space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-2xl font-bold text-white">Uploads</h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Every profile you've fed in, what came out of it, and what to do next.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    placeholder="Search..."
                    className="bg-zinc-950/60 border border-white/10 rounded-lg pl-8 pr-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-white/20 w-44"
                  />
                </div>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white px-3 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 shrink-0"
                >
                  <Plus size={13} /> Add
                </button>
              </div>
            </div>

            {renderAnalyticsPanel()}

            {/* Hidden input reused by every row's screenshot button */}
            <input
              type="file"
              accept="image/*"
              ref={uploadsScreenshotInputRef}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file && uploadsScreenshotTargetId != null) {
                  handleUploadScreenshotForRow(uploadsScreenshotTargetId, file);
                }
                e.target.value = "";
              }}
            />

            <div className="bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-[10px] text-zinc-500 uppercase tracking-wider bg-white/[0.02]">
                      <th className="text-left py-2.5 px-3 font-semibold w-8"></th>
                      <th className="text-left py-2.5 px-3 font-semibold">PDF</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Name</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Company</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Exp</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Replied</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Email</th>
                      <th className="text-left py-2.5 px-3 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredConnections.map(conn => {
                      const isExpanded = expandedUploadRow === conn.id;
                      const hasReplied = !!conn.replied_at || ["replied", "follow_up", "interview"].includes(conn.status);
                      return (
                        <React.Fragment key={conn.id}>
                          <tr className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                            <td className="py-2 px-3">
                              <button
                                onClick={() => setExpandedUploadRow(isExpanded ? null : conn.id)}
                                className="text-zinc-500 hover:text-white cursor-pointer"
                                aria-label={isExpanded ? "Collapse" : "Expand"}
                              >
                                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                              </button>
                            </td>
                            <td className="py-2 px-3 text-zinc-500 font-mono text-[10px] max-w-[140px] truncate" title={conn.pdf_filename || ""}>
                              {conn.pdf_filename || "manual entry"}
                            </td>
                            <td className="py-2 px-3">
                              {conn.profile_url ? (
                                <a
                                  href={conn.profile_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-zinc-100 font-medium hover:text-[#4d8565] hover:underline inline-flex items-center gap-1"
                                >
                                  {conn.name}
                                  <ExternalLink size={10} className="opacity-50" />
                                </a>
                              ) : (
                                <span className="text-zinc-100 font-medium">{conn.name}</span>
                              )}
                              {conn.current_title && (
                                <span className="block text-[10px] text-zinc-500 truncate max-w-[180px]">{conn.current_title}</span>
                              )}
                            </td>
                            <td className="py-2 px-3 text-zinc-400">{conn.company || "-"}</td>
                            <td className="py-2 px-3 text-zinc-400 font-mono">
                              {conn.years_experience ? `${conn.years_experience}y` : "-"}
                            </td>
                            <td className="py-2 px-3">
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                                hasReplied ? "bg-[#4d8565]/15 text-[#7fb894]" : "bg-white/5 text-zinc-500"
                              }`}>
                                {hasReplied ? "Yes" : "No"}
                              </span>
                              {conn.conversation_verdict && (
                                <span className="block text-[9px] text-zinc-500 mt-0.5 capitalize">
                                  {conn.conversation_verdict.replace("_", " ")}
                                </span>
                              )}
                            </td>
                            <td className="py-2 px-3 max-w-[160px]">
                              {conn.candidate_email ? (
                                <span className="text-zinc-400 font-mono text-[10px] truncate block" title={conn.candidate_email}>
                                  {conn.candidate_email}
                                </span>
                              ) : (
                                <span className="text-zinc-600">none found</span>
                              )}
                            </td>
                            <td className="py-2 px-3">
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => {
                                    setUploadsScreenshotTargetId(conn.id);
                                    uploadsScreenshotInputRef.current?.click();
                                  }}
                                  disabled={uploadsRowScreenshotLoadingId === conn.id}
                                  title="Upload a conversation screenshot"
                                  className="p-1.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-400 hover:text-white transition-colors cursor-pointer disabled:opacity-40"
                                >
                                  {uploadsRowScreenshotLoadingId === conn.id
                                    ? <Loader2 size={12} className="animate-spin" />
                                    : <ImagePlus size={12} />}
                                </button>
                                {conn.candidate_email && (
                                  <button
                                    onClick={() => handleGenerateEmail(conn.id)}
                                    disabled={emailDraftLoadingId === conn.id}
                                    title="Draft an outreach email"
                                    className="p-1.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-400 hover:text-white transition-colors cursor-pointer disabled:opacity-40"
                                  >
                                    {emailDraftLoadingId === conn.id
                                      ? <Loader2 size={12} className="animate-spin" />
                                      : <Mail size={12} />}
                                  </button>
                                )}
                                <button
                                  onClick={() => setSelectedConnection(conn)}
                                  title="Open full detail panel"
                                  className="p-1.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-400 hover:text-white transition-colors cursor-pointer"
                                >
                                  <ArrowRight size={12} />
                                </button>
                              </div>
                            </td>
                          </tr>

                          {isExpanded && (
                            <tr className="bg-zinc-950/40">
                              <td colSpan={8} className="px-3 py-4">
                                <div className="space-y-3">
                                  {/* Email draft */}
                                  {conn.generated_email_body && (
                                    <div className="bg-zinc-950/60 border border-white/10 rounded-lg p-3">
                                      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                                        <span className="text-[10px] font-bold text-white uppercase tracking-wider">Email Draft</span>
                                        <div className="flex gap-1.5">
                                          <button
                                            onClick={() => handleCopyClipboard(
                                              `Subject: ${conn.generated_email_subject}\n\n${conn.generated_email_body}`
                                            )}
                                            className="text-[10px] bg-white/5 hover:bg-white/10 border border-white/10 px-2 py-1 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer flex items-center gap-1"
                                          >
                                            <Copy size={10} /> Copy
                                          </button>
                                          <button
                                            onClick={() => openEmailClient(conn)}
                                            className="text-[10px] bg-[#4d8565]/15 hover:bg-[#4d8565]/25 border border-[#4d8565]/30 px-2 py-1 rounded text-[#7fb894] transition-colors cursor-pointer flex items-center gap-1"
                                          >
                                            <Mail size={10} /> Open in {emailClientPreference === "outlook" ? "Outlook" : emailClientPreference === "gmail" ? "Gmail" : "mail app"}
                                          </button>
                                          <button
                                            onClick={() => handleGenerateEmail(conn.id)}
                                            disabled={emailDraftLoadingId === conn.id}
                                            className="text-[10px] bg-white/5 hover:bg-white/10 border border-white/10 px-2 py-1 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer disabled:opacity-40 flex items-center gap-1"
                                          >
                                            <RefreshCw size={10} className={emailDraftLoadingId === conn.id ? "animate-spin" : ""} /> Redraft
                                          </button>
                                        </div>
                                      </div>
                                      <p className="text-[11px] text-zinc-400 font-mono mb-1.5">
                                        <span className="text-zinc-600">Subject:</span> {conn.generated_email_subject}
                                      </p>
                                      <pre className="text-[11px] text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
                                        {conn.generated_email_body}
                                      </pre>
                                    </div>
                                  )}

                                  {/* LinkedIn DM drafts, compact and copy-pasteable */}
                                  {conn.generated_outreach_referral && (
                                    <div className="grid sm:grid-cols-2 gap-2">
                                      {[
                                        { label: "Referral", text: conn.generated_outreach_referral },
                                        { label: "Coffee Chat", text: conn.generated_outreach_coffee },
                                        { label: "Technical", text: conn.generated_outreach_technical },
                                        { label: "Relationship", text: conn.generated_outreach_relationship },
                                        { label: "Featured", text: conn.generated_outreach_featured },
                                      ].filter(d => d.text).map(d => (
                                        <div key={d.label} className="bg-zinc-950/60 border border-white/10 rounded-lg p-2.5">
                                          <div className="flex items-center justify-between mb-1">
                                            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider">{d.label}</span>
                                            <button
                                              onClick={() => handleCopyClipboard(d.text)}
                                              className="text-zinc-500 hover:text-white transition-colors cursor-pointer"
                                              title="Copy"
                                            >
                                              <Copy size={10} />
                                            </button>
                                          </div>
                                          <p className="text-[10px] text-zinc-400 leading-relaxed line-clamp-4 whitespace-pre-wrap">{d.text}</p>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  {conn.conversation_verdict_reason && (
                                    <div className="bg-zinc-950/60 border border-white/10 rounded-lg p-3">
                                      <span className="text-[10px] font-bold text-white uppercase tracking-wider block mb-1">Conversation Read</span>
                                      <p className="text-[11px] text-zinc-400">{conn.conversation_verdict_reason}</p>
                                      {conn.conversation_recommended_action && (
                                        <p className="text-[11px] text-zinc-300 italic mt-1">→ {conn.conversation_recommended_action}</p>
                                      )}
                                    </div>
                                  )}

                                  {!conn.generated_email_body && !conn.generated_outreach_referral && (
                                    <p className="text-[10px] text-zinc-600 font-mono">
                                      Nothing generated yet. This profile may still be in the queue.
                                    </p>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                    {filteredConnections.length === 0 && (
                      <tr>
                        <td colSpan={8} className="text-center py-12 text-zinc-600 font-mono text-[11px]">
                          No uploads yet. Add a profile from the Outreach Target page.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* VIEW B: TWINAGENT PERSONAL SETTINGS */}
        {currentView === "twinagent" && (
          <div className="p-4 sm:p-8 max-w-4xl w-full mx-auto space-y-8">
            <div className="border-b border-zinc-800 pb-4">
              <h2 className="text-2xl font-bold text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-zinc-400">
                TwinAgent Professional Persona Configuration
              </h2>
              <p className="text-xs text-zinc-400 mt-1">
                Compile your professional details, LaTeX source code, and target profiles. TwinAgent feeds this directly to generation workers.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* PDF Resume Drag Zone */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white mb-2 flex items-center space-x-2">
                    <FileText size={16} className="text-zinc-400" />
                    <span>Upload Resume PDF</span>
                  </h3>
                  <p className="text-xs text-zinc-400 mb-6">
                    Parsing your PDF resume imports raw text data, enabling structural relevance matching.
                  </p>
                </div>
                
                <div className="border border-dashed border-zinc-800 hover:border-zinc-700 rounded-lg p-8 text-center bg-zinc-950/50 hover:bg-zinc-950 transition-colors flex flex-col items-center justify-center group">
                  <input 
                    type="file" 
                    accept=".pdf"
                    ref={resumeInputRef}
                    onChange={handleResumeUpload}
                    className="hidden"
                  />
                  <button 
                    onClick={() => resumeInputRef.current?.click()}
                    disabled={resumeUploadLoading}
                    className="text-xs bg-zinc-900 border border-zinc-800 hover:border-zinc-700 px-4 py-2 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {resumeUploadLoading ? "Uploading & Parsing..." : "Choose PDF File"}
                  </button>
                  <span className="text-[10px] text-zinc-500 mt-2 block font-mono">Supports up to 5MB PDF</span>
                </div>
              </div>

              {/* Basic Meta Inputs */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
                <h3 className="text-sm font-semibold text-white mb-2">Job Search Details</h3>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Target Roles</label>
                  <input 
                    type="text" 
                    value={targetRoles}
                    onChange={e => setTargetRoles(e.target.value)}
                    placeholder="e.g. Software Engineer, Full Stack, AI Platform Eng"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Job Search / Visa Status</label>
                  <input 
                    type="text" 
                    value={jobSearchStatus}
                    onChange={e => setJobSearchStatus(e.target.value)}
                    placeholder="e.g. Active job search on OPT visa"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Primary Learning Goals</label>
                  <input 
                    type="text" 
                    value={learningGoals}
                    onChange={e => setLearningGoals(e.target.value)}
                    placeholder="e.g. distributed systems, database design, AI Agent safety"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
              </div>
            </div>

            {/* LaTeX paste code box */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
              <h3 className="text-sm font-semibold text-white mb-2 flex items-center space-x-2">
                <FileText size={16} className="text-emerald-400" />
                <span>Resume LaTeX Code Source (Avoids context loss)</span>
              </h3>
              <p className="text-xs text-zinc-400 mb-4">
                Pasting LaTeX markup allows TwinAgent to inspect details with zero structural formatting bugs.
              </p>
              <textarea 
                value={latexCode}
                onChange={e => setLatexCode(e.target.value)}
                rows={10}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs font-mono text-emerald-400 focus:outline-none focus:border-emerald-500/50"
                placeholder="Paste your resume latex syntax block here..."
              />
            </div>

            {/* Tone Guidelines */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
              <h3 className="text-sm font-semibold text-white mb-2">Outreach Tone Guidelines & Examples</h3>
              <p className="text-xs text-zinc-400 mb-4">
                Paste examples of successful or personal messages you have previously sent. TwinAgent will mimic your exact writing pattern.
              </p>
              <textarea 
                value={toneExamples}
                onChange={e => setToneExamples(e.target.value)}
                rows={4}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                placeholder="e.g., Hi name, loved your post on X. I'm also looking into Y. Would you be open to a quick call next week?"
              />
            </div>

            <div className="flex justify-end pt-4">
              <button 
                onClick={handleSaveSettings}
                disabled={settingsSaveLoading}
                className="bg-zinc-900 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 text-sm font-semibold px-6 py-3 rounded-lg transition-colors cursor-pointer shadow-lg disabled:opacity-50"
              >
                {settingsSaveLoading ? "Saving Persona..." : "Save TwinAgent Configuration"}
              </button>

            </div>
          </div>
        )}

        {/* VIEW C: API KEYS & WORKERTHREADS POOL */}
        {currentView === "apikeys" && (
          <div className="p-4 sm:p-8 max-w-4xl w-full mx-auto space-y-8">
            <div className="border-b border-zinc-800 pb-4">
              <h2 className="text-2xl font-bold text-white flex items-center justify-between">
                <span>Gemini API Key Workers Pool</span>
                <span className="text-xs font-normal text-zinc-400">
                  {keys.length} Keys Configured
                </span>
              </h2>
              <p className="text-xs text-zinc-400 mt-1">
                Configure your Google AI Studio API Keys. We allocate one background **WorkerThread** per active primary API key, running them parallelly.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Add Key Form */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 md:col-span-1 h-fit">
                <h3 className="text-sm font-semibold text-white mb-4">Add API Key</h3>
                <form onSubmit={handleAddApiKey} className="space-y-4">
                  <div>
                    <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Key Value</label>
                    <input 
                      type="password"
                      value={newKeyVal}
                      onChange={e => setNewKeyVal(e.target.value)}
                      placeholder="AIzaSy..."
                      required
                      className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Key Role</label>
                    <select 
                      value={newKeyRole}
                      onChange={e => setNewKeyRole(e.target.value as any)}
                      className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-violet-500 cursor-pointer"
                    >
                      <option value="primary">Primary (Rotates in round-robin)</option>
                      <option value="standby">Standby (Failover Reserve)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Label / Alias</label>
                    <input 
                      type="text"
                      value={newKeyLabel}
                      onChange={e => setNewKeyLabel(e.target.value)}
                      placeholder="e.g. Account A - Project 1"
                      className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <button 
                    type="submit"
                    className="w-full bg-zinc-900 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 text-xs font-semibold py-2.5 rounded transition-colors cursor-pointer shadow-lg"
                  >
                    Register Key
                  </button>

                </form>
              </div>

              {/* Keys List */}
              <div className="md:col-span-2 space-y-4">
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                  <h3 className="text-sm font-semibold text-white mb-4">Configured Key Workers</h3>
                  
                  <div className="space-y-3">
                    {keys.map(k => {
                      const isCooldown = k.cooldown_until && new Date(k.cooldown_until) > new Date();
                      return (
                        <div key={k.id} className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 flex items-center justify-between gap-4">
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="text-xs font-bold text-white">{k.label || "Gemini Key"}</span>
                              <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold uppercase ${
                                k.role === "primary" ? "bg-violet-500/10 text-violet-400 border border-violet-500/20" : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              }`}>
                                {k.role}
                              </span>
                            </div>
                            <span className="text-[10px] text-zinc-500 block font-mono mt-1">Key ID: {k.id} • Registered {new Date(k.created_at).toLocaleDateString()}</span>
                          </div>

                          <div className="flex items-center space-x-3">
                            {isCooldown ? (
                              <span className="text-[9px] font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2 py-1 rounded">
                                Rate Limited / Cooldown
                              </span>
                            ) : (
                              <span className={`text-[9px] font-mono px-2 py-1 rounded ${
                                k.is_active ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800 text-zinc-500 border border-zinc-700"
                              }`}>
                                {k.is_active ? "Ready" : "Disabled"}
                              </span>
                            )}
                            
                            <button 
                              onClick={() => handleToggleKey(k.id)}
                              className="text-[10px] bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-2.5 py-1.5 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer"
                            >
                              {k.is_active ? "Disable" : "Enable"}
                            </button>

                            <button 
                              onClick={() => handleDeleteKey(k.id)}
                              className="p-1.5 hover:bg-rose-950/20 rounded text-zinc-500 hover:text-rose-400 transition-colors cursor-pointer"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {keys.length === 0 && (
                      <div className="text-center py-8 border border-dashed border-zinc-800 rounded-lg text-xs text-zinc-500 font-mono">
                        No keys configured. Register a Gemini API key to boot background workers.
                      </div>
                    )}
                  </div>
                </div>

                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 text-xs text-zinc-400 space-y-2">
                  <h4 className="font-semibold text-white">How the QueueOrchestrator Pools Workers</h4>
                  <p>1. If you register 3 primary keys, 3 parallel WorkerThreads are dynamically allocated to run in the background. They concurrently retrieve and process outreach targets.</p>
                  <p>2. Standby keys act as failovers. If a primary worker hits a 429 rate limit error, the Orchestrator instantly replaces it with an available standby key and sets the primary key to cooldown for 3 minutes, preventing stops.</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* VIEW D: TELEGRAM & GENERAL PACING SETTINGS */}
        {currentView === "settings" && (
          <div className="p-4 sm:p-8 max-w-xl w-full mx-auto space-y-8">
            <div className="border-b border-zinc-800 pb-4">
              <h2 className="text-2xl font-bold text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-zinc-400">
                Outreach Pacing & Notifications
              </h2>
              <p className="text-xs text-zinc-400 mt-1">
                Configure Telegram / Slack notification hooks and delay intervals.
              </p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-6">
              
              {/* Telegram config */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <Send size={16} className="text-blue-400" />
                  <span>Telegram Bot Integration</span>
                </h3>
                <p className="text-xs text-zinc-400">
                  Workers will send generated drafts straight to your private Telegram chat. Create a bot using `@BotFather` to get a token.
                </p>

                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Telegram Bot Token</label>
                  <input 
                    type="password"
                    value={telegramToken}
                    onChange={e => setTelegramToken(e.target.value)}
                    placeholder="e.g. 5219481239:AAEtG2B..."
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Chat ID</label>
                  <input 
                    type="text"
                    value={telegramChatId}
                    onChange={e => setTelegramChatId(e.target.value)}
                    placeholder="e.g. 192847123"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
              </div>

              <hr className="border-zinc-800" />

              {/* Slack config */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <Send size={16} className="text-emerald-400" />
                  <span>Slack Integration</span>
                </h3>
                <p className="text-xs text-zinc-400">
                  Workers will post generated drafts to a Slack channel via an Incoming Webhook. Create one at <span className="font-mono text-zinc-300">api.slack.com/apps</span> &rarr; your app &rarr; Incoming Webhooks &rarr; Add New Webhook.
                </p>

                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Slack Incoming Webhook URL</label>
                  <input
                    type="password"
                    value={slackWebhookUrl}
                    onChange={e => setSlackWebhookUrl(e.target.value)}
                    placeholder="https://hooks.slack.com/services/..."
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                </div>
              </div>

              <hr className="border-zinc-800" />

              {/* Email client preference */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                  <Mail size={16} className="text-zinc-400" />
                  <span>Email Client</span>
                </h3>
                <p className="text-xs text-zinc-400">
                  Where "Open in..." sends your generated email drafts. Nothing is ever sent automatically, the draft opens for you to review first.
                </p>
                <div className="flex flex-wrap gap-2">
                  {[
                    { val: "gmail", label: "Gmail" },
                    { val: "outlook", label: "Outlook" },
                    { val: "default", label: "System default" },
                  ].map(opt => (
                    <button
                      key={opt.val}
                      onClick={() => setEmailClientPreference(opt.val)}
                      className={`px-3 py-2 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                        emailClientPreference === opt.val
                          ? "bg-white/10 border-white/20 text-white"
                          : "bg-zinc-950/60 border-white/10 text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <hr className="border-zinc-800" />

              {/* Queue Pacing */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-white">Queue Pacing Controls</h3>
                <p className="text-xs text-zinc-400">
                  Configure the sleep delay (in minutes) a worker thread takes after completing an outreach task to pace operations.
                </p>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Pacing Interval (Minutes)</label>
                  <input 
                    type="number"
                    value={pacingInterval}
                    onChange={e => setPacingInterval(e.target.value)}
                    min="0"
                    step="0.5"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                  />
                  <span className="text-[10px] text-zinc-500 mt-1 block">Set to 0.5 (30 seconds) for rapid testing.</span>
                </div>
              </div>

              <div className="flex justify-end items-center pt-4 space-x-3">
                <button 
                  onClick={handleTestTelegram}
                  disabled={telegramTestLoading}
                  className="bg-zinc-800 hover:bg-zinc-800 text-xs font-semibold text-zinc-300 hover:text-white px-4 py-2.5 rounded border border-zinc-700 hover:border-zinc-600 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {telegramTestLoading ? "Testing..." : "Test Telegram Connection"}
                </button>
                <button
                  onClick={handleTestSlack}
                  disabled={slackTestLoading}
                  className="bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-300 hover:text-white px-4 py-2.5 rounded border border-zinc-700 hover:border-zinc-600 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {slackTestLoading ? "Testing..." : "Test Slack Connection"}
                </button>
                <button
                  onClick={handleSaveSettings}
                  className="bg-zinc-900 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 text-xs font-semibold px-4 py-2.5 rounded transition-colors cursor-pointer shadow-lg"
                >
                  Save Configuration
                </button>

              </div>

              {telegramTestMessage && (
                <div className="text-xs text-emerald-400 bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-3 mt-3">
                  {telegramTestMessage}
                </div>
              )}
              {telegramTestError && (
                <div className="text-xs text-rose-400 bg-rose-950/20 border border-rose-900/30 rounded-lg p-3 mt-3">
                  {telegramTestError}
                </div>
              )}
              {slackTestMessage && (
                <div className="text-xs text-emerald-400 bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-3 mt-3">
                  {slackTestMessage}
                </div>
              )}
              {slackTestError && (
                <div className="text-xs text-rose-400 bg-rose-950/20 border border-rose-900/30 rounded-lg p-3 mt-3">
                  {slackTestError}
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIEW E: INSIGHTS / ANALYTICS */}
        {currentView === "pipeline" && homeTab === "dashboard" && (
          <div className="p-4 sm:p-8 max-w-5xl w-full mx-auto space-y-6">
            <div className="border-b border-zinc-800 pb-4 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">Dashboard</h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Aggregate view across everyone you've added, so patterns show up without re-reading every card.
                </p>
              </div>
              <button
                onClick={fetchAnalytics}
                className="text-xs bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-3 py-1.5 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer flex items-center gap-1.5 shrink-0"
              >
                <RefreshCw size={12} className={analyticsLoading ? "animate-spin" : ""} />
                <span>Refresh</span>
              </button>
            </div>

            {!analyticsData && (
              <div className="text-center py-16 text-xs text-zinc-500 font-mono">
                {analyticsLoading ? "Loading insights..." : "No data yet."}
              </div>
            )}

            {analyticsData && (() => {
              const people: any[] = analyticsData.people || [];
              const inRange = (cc: number | null) => {
                const c = cc || 0;
                if (connCountRangeFilter === "under_200") return c < 200;
                if (connCountRangeFilter === "200_500") return c >= 200 && c <= 500;
                if (connCountRangeFilter === "500_1000") return c > 500 && c <= 1000;
                if (connCountRangeFilter === "1000_plus") return c > 1000;
                return true;
              };
              const filteredPeople = people.filter(p =>
                inRange(p.connection_count) &&
                (seniorityFilter === "all" || p.seniority === seniorityFilter)
              );
              const replyBuckets = analyticsData.reply_time_buckets || {};
              const bySeniority: Record<string, number> = analyticsData.by_seniority || {};
              const byStatus: Record<string, number> = analyticsData.by_status || {};

              const replyScore = analyticsData.reply_score || {};

              return (
                <>
                  {renderAnalyticsPanel()}

                  {/* Reply score: the headline number, plus what to do about it */}
                  <div className="bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-xl p-5">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div>
                        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Reply Score</span>
                        <div className="flex items-baseline gap-2">
                          <span className={`text-4xl font-bold ${
                            replyScore.reply_rate == null ? "text-zinc-600" :
                            replyScore.reply_rate >= 30 ? "text-[#7fb894]" :
                            replyScore.reply_rate >= 15 ? "text-amber-400" : "text-rose-400"
                          }`}>
                            {replyScore.reply_rate == null ? "n/a" : `${replyScore.reply_rate}%`}
                          </span>
                          <span className="text-xs text-zinc-500 font-mono">
                            {replyScore.replied_count || 0} of {replyScore.sent_count || 0} sent
                          </span>
                        </div>
                      </div>
                      <div className="text-[11px] text-zinc-400 max-w-md leading-relaxed">
                        {replyScore.sent_count === 0
                          ? "Nothing marked as Sent yet. Mark a connection Sent after you actually message them, and this starts tracking."
                          : replyScore.reply_rate >= 30
                          ? "That is a strong rate for cold outreach. Whatever you are doing on targeting and tone, keep doing it."
                          : replyScore.reply_rate >= 15
                          ? "Roughly average for cold outreach. The targets below tend to convert better than a broad spread."
                          : "On the low side. Usually that means targeting too senior, or the ask in the first message is too big. Look at who did reply below for the pattern."}
                      </div>
                    </div>

                    {(replyScore.who_replied?.length > 0 || replyScore.suggested_targets?.length > 0) && (
                      <div className="grid sm:grid-cols-2 gap-4 mt-5 pt-4 border-t border-white/5">
                        {replyScore.who_replied?.length > 0 && (
                          <div>
                            <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-2">
                              Who actually replied
                            </span>
                            <div className="space-y-1.5">
                              {replyScore.who_replied.map((p: any) => (
                                <div key={p.id} className="flex items-center justify-between gap-2 text-[11px]">
                                  {p.profile_url ? (
                                    <a href={p.profile_url} target="_blank" rel="noopener noreferrer"
                                       className="text-zinc-300 hover:text-[#7fb894] hover:underline truncate inline-flex items-center gap-1">
                                      {p.name} <ExternalLink size={9} className="opacity-50 shrink-0" />
                                    </a>
                                  ) : (
                                    <span className="text-zinc-300 truncate">{p.name}</span>
                                  )}
                                  <span className="text-zinc-600 font-mono text-[10px] shrink-0">{p.seniority || "?"}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {replyScore.suggested_targets?.length > 0 && (
                          <div>
                            <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-2">
                              Reach out to these next
                            </span>
                            <div className="space-y-1.5">
                              {replyScore.suggested_targets.map((p: any) => (
                                <div key={p.id} className="flex items-center justify-between gap-2 text-[11px]">
                                  {p.profile_url ? (
                                    <a href={p.profile_url} target="_blank" rel="noopener noreferrer"
                                       className="text-zinc-300 hover:text-[#7fb894] hover:underline truncate inline-flex items-center gap-1">
                                      {p.name} <ExternalLink size={9} className="opacity-50 shrink-0" />
                                    </a>
                                  ) : (
                                    <span className="text-zinc-300 truncate">{p.name}</span>
                                  )}
                                  <span className="text-zinc-600 font-mono text-[10px] shrink-0">
                                    {p.networking_score ? `${p.networking_score}/10` : ""}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Top stat tiles */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Total Outreach</span>
                      <span className="text-2xl font-bold text-white">{analyticsData.total}</span>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Replied</span>
                      <span className="text-2xl font-bold text-emerald-400">{byStatus["replied"] || 0}</span>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">10+ Yrs Experience</span>
                      <span className="text-2xl font-bold text-white">{analyticsData.experienced_10_plus}</span>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Recruiters Contacted</span>
                      <span className="text-2xl font-bold text-white">{bySeniority["Recruiter"] || 0}</span>
                    </div>
                  </div>

                  {/* Pipeline breakdown + Seniority breakdown */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3">Pipeline Breakdown</h3>
                      <div className="space-y-1.5">
                        {Object.entries(byStatus).map(([status, count]) => (
                          <div key={status} className="flex justify-between items-center text-xs">
                            <span className="text-zinc-400 capitalize">{status.replace("_", " ")}</span>
                            <span className="text-zinc-200 font-mono font-semibold">{count as number}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3">Seniority Mix</h3>
                      <div className="space-y-1.5">
                        {Object.entries(bySeniority).map(([seniority, count]) => (
                          <div key={seniority} className="flex justify-between items-center text-xs">
                            <span className="text-zinc-400">{seniority}</span>
                            <span className="text-zinc-200 font-mono font-semibold">{count as number}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Reply-time analysis */}
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3">Reply-Time Analysis</h3>
                    <p className="text-[10px] text-zinc-500 mb-3">
                      Only counts connections marked "Sent" through the funnel stage selector, since that's what timestamps the clock start.
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="bg-zinc-950 border border-emerald-900/30 rounded-lg p-3 text-center">
                        <span className="text-lg font-bold text-emerald-400 block">{replyBuckets.within_a_day || 0}</span>
                        <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Within a day</span>
                      </div>
                      <div className="bg-zinc-950 border border-amber-900/30 rounded-lg p-3 text-center">
                        <span className="text-lg font-bold text-amber-400 block">{replyBuckets.within_a_week || 0}</span>
                        <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Within a week</span>
                      </div>
                      <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-center">
                        <span className="text-lg font-bold text-zinc-300 block">{replyBuckets.longer_than_a_week || 0}</span>
                        <span className="text-[9px] text-zinc-500 uppercase tracking-wider">Longer than a week</span>
                      </div>
                      <div className="bg-zinc-950 border border-rose-900/30 rounded-lg p-3 text-center">
                        <span className="text-lg font-bold text-rose-400 block">{replyBuckets.no_reply_yet || 0}</span>
                        <span className="text-[9px] text-zinc-500 uppercase tracking-wider">No reply, 7+ days</span>
                      </div>
                    </div>
                  </div>

                  {/* Filterable people list */}
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider">Everyone ({filteredPeople.length})</h3>
                      <div className="flex flex-wrap gap-2">
                        <select
                          value={connCountRangeFilter}
                          onChange={e => setConnCountRangeFilter(e.target.value)}
                          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-[11px] text-zinc-300 focus:outline-none focus:border-zinc-700"
                        >
                          <option value="all">Any connection count</option>
                          <option value="under_200">Under 200</option>
                          <option value="200_500">200 to 500</option>
                          <option value="500_1000">500 to 1000</option>
                          <option value="1000_plus">1000+</option>
                        </select>
                        <select
                          value={seniorityFilter}
                          onChange={e => setSeniorityFilter(e.target.value)}
                          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-[11px] text-zinc-300 focus:outline-none focus:border-zinc-700"
                        >
                          <option value="all">Any seniority</option>
                          {Object.keys(bySeniority).map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-zinc-800 text-[10px] text-zinc-500 uppercase tracking-wider">
                            <th className="text-left py-2 pr-3">Name</th>
                            <th className="text-left py-2 pr-3">Company</th>
                            <th className="text-left py-2 pr-3">Seniority</th>
                            <th className="text-left py-2 pr-3">Connections</th>
                            <th className="text-left py-2 pr-3">Status</th>
                            <th className="text-left py-2 pr-3">Conversation Read</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredPeople.map(p => (
                            <tr
                              key={p.id}
                              onClick={() => {
                                const full = connections.find(c => c.id === p.id);
                                if (full) setSelectedConnection(full);
                              }}
                              className="border-b border-zinc-900 hover:bg-zinc-950/60 cursor-pointer"
                            >
                              <td className="py-2 pr-3 text-zinc-200 font-medium">{p.name}</td>
                              <td className="py-2 pr-3 text-zinc-400">{p.company || "-"}</td>
                              <td className="py-2 pr-3 text-zinc-400">{p.seniority}</td>
                              <td className="py-2 pr-3 text-zinc-400 font-mono">{p.connection_count ?? "-"}</td>
                              <td className="py-2 pr-3 text-zinc-400 capitalize">{p.status.replace("_", " ")}</td>
                              <td className="py-2 pr-3">
                                {p.conversation_verdict ? (
                                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                                    p.conversation_verdict === "interested" ? "bg-emerald-500/10 text-emerald-400" :
                                    p.conversation_verdict === "lukewarm" ? "bg-amber-500/10 text-amber-400" :
                                    p.conversation_verdict === "not_interested" ? "bg-rose-500/10 text-rose-400" :
                                    "bg-zinc-800 text-zinc-400"
                                  }`}>
                                    {p.conversation_verdict.replace("_", " ")}
                                  </span>
                                ) : (
                                  <span className="text-zinc-600">-</span>
                                )}
                              </td>
                            </tr>
                          ))}
                          {filteredPeople.length === 0 && (
                            <tr>
                              <td colSpan={6} className="text-center py-8 text-zinc-600 font-mono text-[10px]">
                                No one matches this filter.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              );
            })()}
          </div>
        )}

      </main>

      {/* 3. FLOATING DETAIL PANEL (Clicking Kanban Card Opens this sidebar) */}
      {selectedConnection && (
        <div className="fixed lg:static inset-0 lg:inset-auto w-full lg:w-[520px] border-l border-zinc-800 bg-zinc-900 lg:bg-zinc-900/90 backdrop-blur z-30 flex flex-col shrink-0">
          
          {/* Header */}
          <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-bold text-white">{selectedConnection.name}</h2>
                <button 
                  onClick={() => handleToggleStar(selectedConnection.id)}
                  className={`p-1 rounded hover:bg-zinc-800 ${selectedConnection.is_starred ? "text-amber-400" : "text-zinc-500"}`}
                >
                  <Star size={16} fill={selectedConnection.is_starred ? "currentColor" : "none"} />
                </button>
              </div>
              {(selectedConnection.current_title || selectedConnection.company) && (
                <p className="text-xs text-zinc-400 mt-1">
                  {[selectedConnection.current_title, selectedConnection.company].filter(Boolean).join(" • ")}
                </p>
              )}
              {selectedConnection.profile_url && (
                <a 
                  href={selectedConnection.profile_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center space-x-1 text-[10px] text-zinc-400 hover:text-white font-semibold hover:underline bg-zinc-900 px-2 py-1 border border-zinc-800 rounded"
                >
                  <span>View LinkedIn Profile ↗</span>
                </a>
              )}
            </div>
            
            <button 
              onClick={() => setSelectedConnection(null)}
              className="text-xs text-zinc-500 hover:text-white px-3 py-1.5 border border-zinc-800 hover:border-zinc-700 bg-zinc-950/40 rounded transition-colors cursor-pointer"
            >
              Close
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            
            {/* Stage Selector */}
            <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
              <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-2">Funnel Stage</label>
              <div className="grid grid-cols-3 gap-2">
                {["pending", "completed", "sent", "replied", "follow_up", "interview", "closed"].map(st => (
                  <button
                    key={st}
                    onClick={() => handleUpdateStatus(selectedConnection.id, st)}
                    className={`py-1.5 rounded text-[10px] font-mono font-semibold uppercase border transition-colors cursor-pointer ${
                      selectedConnection.status === st
                        ? "bg-zinc-800 text-white border-zinc-700 font-bold"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {st === "completed" ? "Draft Ready" : st === "replied" ? "Replied" : st === "follow_up" ? "Follow Up" : st}
                  </button>
                ))}
              </div>
            </div>

            {/* Networking Intelligence Signals */}
            <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-4">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-zinc-800 pb-2">
                Networking Intelligence Signals
              </h3>
              
              <div className="grid grid-cols-2 gap-4">
                {/* Networking Score */}
                <div className="space-y-1">
                  <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Networking Score</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-bold text-white font-mono">{selectedConnection.networking_score || "5.0"}</span>
                    <div className="flex items-center space-x-0.5">
                      {[...Array(5)].map((_, i) => {
                        const scoreVal = (selectedConnection.networking_score || 5.0) / 2.0;
                        const filled = i < Math.round(scoreVal);
                        return (
                          <Star 
                            key={i} 
                            size={12} 
                            className={filled ? "text-amber-400 fill-amber-400" : "text-zinc-700"} 
                          />
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Reply Probability progress/gauge */}
                <div className="space-y-1">
                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-zinc-500 font-semibold uppercase tracking-wider block">Reply Probability</span>
                    <span className={`font-mono font-bold ${
                      (selectedConnection.reply_probability || 50) >= 75 ? "text-emerald-400" : 
                      (selectedConnection.reply_probability || 50) >= 40 ? "text-amber-400" : "text-rose-400"
                    }`}>
                      {Math.round(selectedConnection.reply_probability || 50)}%
                    </span>
                  </div>
                  <div className="w-full bg-zinc-900 h-2 rounded-full overflow-hidden border border-zinc-800/80">
                    <div 
                      className={`h-full rounded-full transition-all duration-500 ${
                        (selectedConnection.reply_probability || 50) >= 75 ? "bg-gradient-to-r from-emerald-600 to-emerald-400" : 
                        (selectedConnection.reply_probability || 50) >= 40 ? "bg-gradient-to-r from-amber-600 to-amber-400" : 
                        "bg-gradient-to-r from-rose-600 to-rose-400"
                      }`}
                      style={{ width: `${selectedConnection.reply_probability || 50}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-900">
                {/* Decision Maker Badge */}
                <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-center">
                  <span className="text-[8px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Decision Maker</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                    selectedConnection.is_decision_maker === "yes" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                    selectedConnection.is_decision_maker === "partial" ? "bg-zinc-900 text-zinc-400 border border-zinc-800" :
                    "bg-zinc-800 text-zinc-400"
                  }`}>
                    {(selectedConnection.is_decision_maker || "no").toUpperCase()}
                  </span>
                </div>

                {/* Referral Potential Badge */}
                <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-center">
                  <span className="text-[8px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Referral Potential</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                    selectedConnection.referral_potential === "high" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                    selectedConnection.referral_potential === "medium" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" :
                    "bg-zinc-800 text-zinc-400"
                  }`}>
                    {(selectedConnection.referral_potential || "medium").toUpperCase()}
                  </span>
                </div>

                {/* Hiring Badge Status */}
                {(() => {
                  let hiringBadge = "OFF";
                  try {
                    const pIntel = JSON.parse(selectedConnection.profile_intelligence || "{}");
                    hiringBadge = pIntel.hiring_badge_status || "OFF";
                  } catch(e) {}
                  return (
                    <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-center">
                      <span className="text-[8px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Hiring Badge</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        hiringBadge === "ON" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-pulse" :
                        "bg-zinc-800 text-zinc-500"
                      }`}>
                        {hiringBadge}
                      </span>
                    </div>
                  );
                })()}
              </div>

              {selectedConnection.networking_difficulty && (
                <div className="flex justify-between items-center text-[10px] pt-1">
                  <span className="text-zinc-500 font-semibold uppercase tracking-wider font-mono">Networking Difficulty</span>
                  <span className={`font-bold uppercase font-mono ${
                    selectedConnection.networking_difficulty === "easy" ? "text-emerald-400" :
                    selectedConnection.networking_difficulty === "medium" ? "text-amber-400" :
                    selectedConnection.networking_difficulty === "hard" ? "text-orange-400" : "text-rose-400"
                  }`}>
                    {selectedConnection.networking_difficulty.replace('_', ' ')}
                  </span>
                </div>
              )}
            </div>

            {/* Context & Reasoning Summary */}
            {selectedConnection.context_summary && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-2">
                <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Reasoning Context Summary</span>
                <p className="text-xs text-zinc-200 bg-zinc-900 border border-zinc-800/80 rounded-lg p-3.5 leading-relaxed italic">
                  "{selectedConnection.context_summary}"
                </p>
              </div>
            )}

            {/* Multi-Agent Intelligence Tabs */}
            {selectedConnection.profile_intelligence && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-4">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-zinc-800 pb-2">Outreach Agent Intelligence</h3>
                
                {/* Tabs selection */}
                <div className="flex bg-zinc-900 p-1 rounded-lg border border-zinc-800 overflow-x-auto gap-1">
                  {[
                    { id: "profile", label: "Profile" },
                    { id: "company", label: "Company" },
                    { id: "strategy", label: "Strategy" },
                    { id: "personalization", label: "Hooks" }
                  ].map(tab => (
                    <button 
                      key={tab.id}
                      onClick={() => setIntelTab(tab.id as any)}
                      className={`flex-1 py-1 px-2 text-[9px] font-semibold rounded-md transition-colors cursor-pointer uppercase text-center whitespace-nowrap ${
                        intelTab === tab.id 
                          ? "bg-zinc-800 text-zinc-200 border border-zinc-700 font-bold" 
                          : "text-zinc-500 hover:text-zinc-400"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-xs space-y-3">
                  {intelTab === "profile" && (() => {
                    try {
                      const data = JSON.parse(selectedConnection.profile_intelligence || "{}");
                      return (
                        <div className="space-y-2">
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Seniority</span>
                            <span className="text-white font-medium">{data.seniority || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Experience</span>
                            <span className="text-white font-medium">{data.years_experience ? `${data.years_experience} Yrs` : "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Target Angle</span>
                            <span className="text-zinc-300 font-semibold">{data.best_conversation_angle || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Tone</span>
                            <span className="text-white font-medium italic">{data.tone || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Hiring Probability</span>
                            <span className="text-emerald-400 font-bold">{data.hiring_probability || "N/A"}</span>
                          </div>
                          <div className="pt-1">
                            <span className="text-[10px] text-zinc-500 block mb-1">Technologies</span>
                            <p className="text-[11px] text-zinc-300 font-mono bg-zinc-950 p-1.5 rounded">{data.technologies || "None listed"}</p>
                          </div>
                          {data.screenshot_observations && data.screenshot_observations !== "None" && (
                            <div className="pt-1 border-t border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block mb-1">Screenshot Observations</span>
                              <p className="text-[11px] text-zinc-300 bg-zinc-950 p-1.5 rounded leading-relaxed">{data.screenshot_observations}</p>
                            </div>
                          )}
                        </div>
                      );
                    } catch (e) {
                      return <span className="text-[10px] text-zinc-500">No profile intelligence parsed.</span>;
                    }
                  })()}

                  {intelTab === "company" && (() => {
                    try {
                      const data = JSON.parse(selectedConnection.company_intelligence || "{}");
                      return (
                        <div className="space-y-2">
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Company Type</span>
                            <span className="text-white font-medium">{data.company_type || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Company Stage</span>
                            <span className="text-zinc-300 font-bold">{data.company_stage || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Employee Count</span>
                            <span className="text-white font-medium">{data.employee_count || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Decision Maker Access</span>
                            <span className="text-white font-medium capitalize">{data.decision_maker_accessibility || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Outreach Difficulty</span>
                            <span className="text-amber-400 font-bold">{data.outreach_difficulty || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Expected Response</span>
                            <span className="text-emerald-400 font-bold">{data.expected_response_rate || "N/A"}</span>
                          </div>
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Referrals Friendly</span>
                            <span className="text-white font-medium">{data.referral_friendliness || "N/A"}</span>
                          </div>
                          <div className="pt-1 border-t border-zinc-800/60">
                            <span className="text-[10px] text-zinc-500 block">Engineering Culture</span>
                            <p className="text-[11px] text-zinc-300 mt-1 leading-relaxed">{data.engineering_culture || "N/A"}</p>
                          </div>
                          <div className="pt-1 border-t border-zinc-800/60">
                            <span className="text-[10px] text-zinc-500 block">Hiring Culture</span>
                            <p className="text-[11px] text-zinc-300 mt-1 leading-relaxed">{data.hiring_culture || "N/A"}</p>
                          </div>
                        </div>
                      );
                    } catch (e) {
                      return <span className="text-[10px] text-zinc-500">No company intelligence parsed.</span>;
                    }
                  })()}

                  {intelTab === "strategy" && (() => {
                    try {
                      const data = JSON.parse(selectedConnection.relationship_strategy || "{}");
                      return (
                        <div className="space-y-3">
                          <div className="flex justify-between border-b border-zinc-800 pb-1">
                            <span className="text-[10px] text-zinc-500">Confidence Score</span>
                            <span className="text-zinc-300 font-bold">{data.confidence ? `${Math.round(data.confidence * 100)}%` : "N/A"}</span>
                          </div>
                          
                          <div>
                            <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider block mb-1">✅ Strategy DOs</span>
                            <ul className="list-disc list-inside text-[11px] text-zinc-300 space-y-1">
                              {(data.dos || []).map((doItem: string, idx: number) => (
                                <li key={idx}>{doItem}</li>
                              ))}
                            </ul>
                          </div>
                          
                          <div className="border-t border-zinc-800/60 pt-2">
                            <span className="text-[10px] text-rose-400 font-semibold uppercase tracking-wider block mb-1">❌ Strategy DONTs</span>
                            <ul className="list-disc list-inside text-[11px] text-zinc-300 space-y-1">
                              {(data.donts || []).map((dontItem: string, idx: number) => (
                                <li key={idx}>{dontItem}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      );
                    } catch (e) {
                      return <span className="text-[10px] text-zinc-500">No strategy intelligence parsed.</span>;
                    }
                  })()}

                  {intelTab === "personalization" && (() => {
                    try {
                      const data = JSON.parse(selectedConnection.personalization_data || "{}");
                      return (
                        <div className="space-y-3">
                          {data.motivation_hooks && (
                            <div>
                              <span className="text-[10px] text-zinc-400 font-semibold uppercase tracking-wider block mb-1">Motivation Hooks / Career Transitions</span>
                              <p className="text-[11px] text-zinc-400 leading-relaxed bg-zinc-950 p-2 rounded">{data.motivation_hooks}</p>
                            </div>
                          )}
                          
                          {(selectedConnection.conversation_starter || data.conversation_starter) && (
                            <div>
                              <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider block mb-1">Conversation Starter Highlight</span>
                              <p className="text-[11px] text-zinc-400 leading-relaxed bg-zinc-950 p-2 rounded border border-emerald-950/20">"{selectedConnection.conversation_starter || data.conversation_starter}"</p>
                            </div>
                          )}

                          {(selectedConnection.avoid_points || data.avoid_points) && (
                            <div>
                              <span className="text-[10px] text-rose-400 font-semibold uppercase tracking-wider block mb-1">⚠️ Things to Avoid</span>
                              <p className="text-[11px] text-zinc-400 leading-relaxed bg-zinc-950 p-2 rounded border border-rose-950/20">{selectedConnection.avoid_points || data.avoid_points}</p>
                            </div>
                          )}

                          <div className="border-t border-zinc-800/60 pt-2">
                            <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Suggested Hooks</span>
                            <ul className="list-disc list-inside text-[11px] text-zinc-300 space-y-1">
                              {(data.conversation_hooks || []).map((hook: string, idx: number) => (
                                <li key={idx} className="leading-relaxed">{hook}</li>
                              ))}
                            </ul>
                          </div>
                          {data.highlighted_projects && data.highlighted_projects.length > 0 && (
                            <div className="border-t border-zinc-800/60 pt-2">
                              <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Projects to Reference</span>
                              <ul className="list-disc list-inside text-[11px] text-zinc-300 space-y-1">
                                {data.highlighted_projects.map((proj: string, idx: number) => (
                                  <li key={idx}>{proj}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {data.shared_elements && data.shared_elements.length > 0 && (
                            <div className="border-t border-zinc-800/60 pt-2">
                              <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block mb-1">Mutual Overlaps</span>
                              <ul className="list-disc list-inside text-[11px] text-zinc-300 space-y-1">
                                {data.shared_elements.map((el: string, idx: number) => (
                                  <li key={idx}>{el}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      );
                    } catch (e) {
                      return <span className="text-[10px] text-zinc-500">No personalization hooks parsed.</span>;
                    }
                  })()}
                </div>
              </div>
            )}

            {/* Stage 1 details (Bridge alignment metrics fallback) */}
            {selectedConnection.best_angle && !selectedConnection.profile_intelligence && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-zinc-800 pb-2">Why message this person?</h3>
                <div>
                  <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Best Outreach Angle</span>
                  <span className="text-xs text-violet-400 font-semibold">{selectedConnection.best_angle}</span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Alignment Score / Rationale</span>
                  <p className="text-xs text-zinc-300 mt-0.5 leading-relaxed">{selectedConnection.why_person}</p>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">Direct Commmon Bridge</span>
                  <p className="text-xs text-zinc-300 mt-0.5 leading-relaxed">{selectedConnection.bridge}</p>
                </div>
              </div>
            )}

            {/* Generated Outreach Copy Variants */}
            {selectedConnection.generated_outreach_short && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-4">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-zinc-800 pb-2">Generated Outreach Drafts</h3>
                
                {/* Tabs */}
                <div className="flex bg-zinc-900 p-1 rounded-lg border border-zinc-800 overflow-x-auto gap-1">
                  {[
                    { id: "referral", label: "Referral" },
                    { id: "coffee", label: "Coffee Chat" },
                    { id: "technical", label: "Technical" },
                    { id: "relationship", label: "Relationship" },
                    { id: "featured", label: "Featured" }
                  ].map(tab => (
                    <button 
                      key={tab.id}
                      onClick={() => handleSelectVariant(selectedConnection.id, tab.id)}
                      className={`flex-1 py-1.5 px-2 text-[9px] font-semibold rounded-md transition-colors cursor-pointer uppercase text-center whitespace-nowrap ${
                        selectedVariant === tab.id 
                          ? "bg-zinc-800 text-white border border-zinc-700 font-bold" 
                          : "text-zinc-500 hover:text-zinc-300"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Draft text Area */}
                <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 relative">
                  <p className="text-xs text-zinc-200 whitespace-pre-wrap leading-relaxed font-mono">
                    {selectedVariant === "referral" && (selectedConnection.generated_outreach_referral || selectedConnection.generated_outreach_short)}
                    {selectedVariant === "coffee" && (selectedConnection.generated_outreach_coffee || selectedConnection.generated_outreach_warm)}
                    {selectedVariant === "technical" && (selectedConnection.generated_outreach_technical || selectedConnection.generated_outreach_tech)}
                    {selectedVariant === "relationship" && (selectedConnection.generated_outreach_relationship || selectedConnection.generated_outreach_mixed)}
                    {selectedVariant === "featured" && selectedConnection.generated_outreach_featured}
                    
                    {/* Retro-compatibility Fallbacks */}
                    {selectedVariant === "short" && (selectedConnection.generated_outreach_referral || selectedConnection.generated_outreach_short)}
                    {selectedVariant === "warm" && (selectedConnection.generated_outreach_coffee || selectedConnection.generated_outreach_warm)}
                    {selectedVariant === "tech" && (selectedConnection.generated_outreach_technical || selectedConnection.generated_outreach_tech)}
                    {selectedVariant === "mixed" && (selectedConnection.generated_outreach_relationship || selectedConnection.generated_outreach_mixed)}
                  </p>

                  <div className="flex justify-end items-center space-x-2 mt-4 pt-3 border-t border-zinc-800/80">
                    <button 
                      onClick={() => handleCopyClipboard(
                        selectedVariant === "referral" ? (selectedConnection.generated_outreach_referral || selectedConnection.generated_outreach_short) :
                        selectedVariant === "coffee" ? (selectedConnection.generated_outreach_coffee || selectedConnection.generated_outreach_warm) :
                        selectedVariant === "technical" ? (selectedConnection.generated_outreach_technical || selectedConnection.generated_outreach_tech) :
                        selectedVariant === "relationship" ? (selectedConnection.generated_outreach_relationship || selectedConnection.generated_outreach_mixed) :
                        selectedVariant === "featured" ? (selectedConnection.generated_outreach_featured) :
                        selectedVariant === "short" ? (selectedConnection.generated_outreach_referral || selectedConnection.generated_outreach_short) :
                        selectedVariant === "warm" ? (selectedConnection.generated_outreach_coffee || selectedConnection.generated_outreach_warm) :
                        selectedVariant === "tech" ? (selectedConnection.generated_outreach_technical || selectedConnection.generated_outreach_tech) :
                        (selectedConnection.generated_outreach_relationship || selectedConnection.generated_outreach_mixed)
                      )}
                      className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white px-3 py-1.5 border border-zinc-700 rounded text-[10px] font-semibold flex items-center space-x-1.5 transition-colors cursor-pointer"
                    >
                      {copiedText ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                      <span>{copiedText ? "Copied!" : "Copy Draft"}</span>
                    </button>
                    <button 
                      onClick={() => handleUpdateStatus(selectedConnection.id, "sent")}
                      className="bg-zinc-900 border border-emerald-800/40 text-emerald-400 hover:bg-emerald-950/20 hover:text-emerald-400 hover:border-emerald-700 px-3 py-1.5 rounded text-[10px] font-semibold flex items-center space-x-1.5 transition-colors cursor-pointer"
                    >
                      <Send size={12} />
                      <span>Mark Sent</span>
                    </button>
                  </div>

                </div>
              </div>
            )}

            {/* Conversation Log & Thread Follow-ups */}
            <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-4">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-zinc-800 pb-2 flex items-center space-x-2">
                <MessageSquare size={14} className="text-emerald-400" />
                <span>Thread Interaction Log</span>
              </h3>
              <p className="text-[10px] text-zinc-400">
                Pasting responses here allows the follow-up generator to analyze thread history and suggest responses.
              </p>

              {/* Conversation Quality Verdict, from the most recently analyzed screenshot */}
              {selectedConnection.conversation_verdict && (
                <div className={`rounded-lg p-3 border text-xs space-y-1 ${
                  selectedConnection.conversation_verdict === "interested" ? "bg-emerald-950/20 border-emerald-900/30" :
                  selectedConnection.conversation_verdict === "lukewarm" ? "bg-amber-950/20 border-amber-900/30" :
                  selectedConnection.conversation_verdict === "not_interested" ? "bg-rose-950/20 border-rose-900/30" :
                  "bg-zinc-900 border-zinc-800"
                }`}>
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${
                    selectedConnection.conversation_verdict === "interested" ? "text-emerald-400" :
                    selectedConnection.conversation_verdict === "lukewarm" ? "text-amber-400" :
                    selectedConnection.conversation_verdict === "not_interested" ? "text-rose-400" :
                    "text-zinc-400"
                  }`}>
                    {selectedConnection.conversation_verdict.replace("_", " ")}
                  </span>
                  <p className="text-zinc-300">{selectedConnection.conversation_verdict_reason}</p>
                  {selectedConnection.conversation_recommended_action && (
                    <p className="text-zinc-400 italic">→ {selectedConnection.conversation_recommended_action}</p>
                  )}
                </div>
              )}

              {/* History Messages */}
              <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
                {threadLogs.map(log => (
                  <div
                    key={log.id}
                    className={`p-3 rounded-lg text-xs max-w-[85%] ${
                      log.sender === "user"
                        ? "bg-zinc-900 border border-zinc-800 ml-auto"
                        : "bg-violet-950/20 border border-violet-900/30 mr-auto"
                    }`}
                  >
                    <span className="text-[9px] text-zinc-500 font-semibold block mb-1">
                      {log.sender === "user" ? "You" : selectedConnection.name}
                    </span>
                    {log.screenshot_path ? (
                      <img
                        src={`${BACKEND_URL}/${log.screenshot_path}`}
                        alt="Conversation screenshot"
                        className="rounded-md max-h-48 object-contain border border-zinc-800"
                      />
                    ) : (
                      <p className="text-zinc-200">{log.message}</p>
                    )}
                  </div>
                ))}

                {threadLogs.length === 0 && (
                  <div className="text-center py-6 text-[10px] text-zinc-600 font-mono border border-dashed border-zinc-800 rounded-lg">
                    Log empty. Add replies to seed follow-up context.
                  </div>
                )}
              </div>

              {/* Add Log Box */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 space-y-3">
                <textarea 
                  value={newLogMessage}
                  onChange={e => setNewLogMessage(e.target.value)}
                  placeholder="Paste log message here..."
                  rows={2}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-xs text-zinc-200 focus:outline-none"
                />
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center space-x-1">
                    <button 
                      onClick={() => setLogSender("connection")}
                      className={`px-2 py-1 rounded text-[9px] font-semibold uppercase transition-colors ${
                        logSender === "connection" ? "bg-zinc-800 border border-zinc-700 text-white font-bold" : "bg-zinc-950 text-zinc-500"
                      }`}
                    >
                      Them Replied
                    </button>
                    <button 
                      onClick={() => setLogSender("user")}
                      className={`px-2 py-1 rounded text-[9px] font-semibold uppercase transition-colors ${
                        logSender === "user" ? "bg-zinc-800 border border-emerald-800/40 text-emerald-400 font-bold" : "bg-zinc-950 text-zinc-500"
                      }`}
                    >
                      Me Sent
                    </button>
                  </div>
                  <button
                    onClick={handleAddThreadLog}
                    className="bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 text-zinc-300 hover:text-white px-3 py-1 text-[10px] rounded font-semibold transition-colors cursor-pointer"
                  >
                    Add Message
                  </button>
                </div>
              </div>

              {/* Screenshot upload: has an AI agent read the actual conversation and judge how it's going */}
              <input
                type="file"
                accept="image/*"
                ref={conversationScreenshotInputRef}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleUploadConversationScreenshot(file);
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => conversationScreenshotInputRef.current?.click()}
                disabled={screenshotUploadLoading}
                className="w-full flex items-center justify-center gap-2 bg-zinc-900 border border-dashed border-zinc-700 hover:border-zinc-600 text-zinc-400 hover:text-white px-3 py-2.5 text-[11px] rounded-lg font-semibold transition-colors cursor-pointer disabled:opacity-50"
              >
                <ImagePlus size={13} className={screenshotUploadLoading ? "animate-pulse" : ""} />
                <span>{screenshotUploadLoading ? "Reading conversation..." : "Upload Conversation Screenshot for AI Read"}</span>
              </button>

              {/* Follow-up reply generator */}
              <div className="pt-2 border-t border-zinc-800 space-y-3">
                <h4 className="text-[10px] font-bold text-white uppercase tracking-wider">Generate Follow-up Message</h4>
                <textarea 
                  value={intentInput}
                  onChange={e => setIntentInput(e.target.value)}
                  placeholder="e.g. ask for 15-min chat next Tuesday morning (optional intent)"
                  rows={2}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-xs text-zinc-200 focus:outline-none"
                />
                
                <button 
                  onClick={handleGenerateReply}
                  disabled={isGeneratingReply}
                  className="w-full bg-zinc-900 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 text-xs font-semibold py-2 rounded transition-colors cursor-pointer shadow-lg flex items-center justify-center space-x-2 disabled:opacity-50"
                >
                  <RefreshCw size={12} className={isGeneratingReply ? "animate-spin" : ""} />
                  <span>{isGeneratingReply ? "Thinking..." : "Generate Follow-up Draft"}</span>
                </button>


                {suggestedReply && (
                  <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 relative">
                    <span className="text-[9px] text-emerald-400 font-semibold block mb-1">Suggested Follow-up</span>
                    <p className="text-xs text-zinc-200 leading-relaxed whitespace-pre-wrap">{suggestedReply}</p>
                    <button 
                      onClick={() => handleCopyClipboard(suggestedReply)}
                      className="absolute top-3 right-3 text-zinc-500 hover:text-white p-1 hover:bg-zinc-800 rounded"
                    >
                      <Copy size={12} />
                    </button>
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

      {/* 4. ADD OUTREACH TARGET DIALOG MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
            <h3 className="text-base font-bold text-white mb-4">Add Outreach Target Candidate</h3>
            
            <form onSubmit={handleAddConnection} className="space-y-4">
              
              {/* Profile PDF drag zone */}
              <div className="border border-dashed border-zinc-800 rounded-lg p-4 text-center bg-zinc-950/40 relative">
                <span className="text-xs text-zinc-400 block mb-2">Import from LinkedIn profile PDF (Select one or multiple)</span>
                <input 
                  type="file" 
                  accept=".pdf"
                  multiple
                  ref={fileInputRef}
                  onChange={(e) => {
                    if (e.target.files) {
                      setConnPdfFiles(Array.from(e.target.files));
                    }
                  }}
                  className="hidden"
                />
                {connPdfFiles.length > 0 ? (
                  <div className="text-xs text-emerald-400 font-mono space-y-1">
                    <div className="flex items-center justify-center space-x-2">
                      <Check size={14} />
                      <span>{connPdfFiles.length} Profile PDFs selected</span>
                      <button type="button" onClick={() => setConnPdfFiles([])} className="text-rose-500 hover:underline font-semibold ml-2">Clear</button>
                    </div>
                    <ul className="text-[10px] text-zinc-500 max-h-20 overflow-y-auto text-left list-disc list-inside px-4 mt-2 border-t border-zinc-800 pt-2">
                      {connPdfFiles.map((file, i) => (
                        <li key={i} className="line-clamp-1">{file.name}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <button 
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="text-xs bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-3 py-1.5 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer"
                  >
                    Select PDF Profiles
                  </button>
                )}
                <span className="text-[9px] text-zinc-500 mt-1 block">Uses LinkedIn's Desktop "Save to PDF" file format</span>
              </div>

              {/* Hiring Toggle Override */}
              <div className="space-y-1.5">
                <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider">Hiring Status Override (for this group / profile)</label>
                <div className="flex items-center space-x-4 bg-zinc-950 border border-zinc-800 rounded p-2 text-xs">
                  <label className="flex items-center space-x-2 cursor-pointer text-zinc-300">
                    <input
                      type="radio"
                      name="hiringOverride"
                      value=""
                      checked={customHiringStatus === ""}
                      onChange={() => setCustomHiringStatus("")}
                      className="accent-zinc-500"
                    />
                    <span>Auto Detect (Gemini)</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer text-zinc-300">
                    <input
                      type="radio"
                      name="hiringOverride"
                      value="ON"
                      checked={customHiringStatus === "ON"}
                      onChange={() => setCustomHiringStatus("ON")}
                      className="accent-zinc-500"
                    />
                    <span>Hiring (Yes)</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer text-zinc-300">
                    <input
                      type="radio"
                      name="hiringOverride"
                      value="OFF"
                      checked={customHiringStatus === "OFF"}
                      onChange={() => setCustomHiringStatus("OFF")}
                      className="accent-zinc-500"
                    />
                    <span>Not Hiring (No)</span>
                  </label>
                </div>
              </div>

              {/* Connection Count Override */}
              <div className="space-y-1.5">
                <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider">Connection Count Override (Optional)</label>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    { label: "Under 300", val: 200 },
                    { label: "300 to 500", val: 400 },
                    { label: "500+", val: 550 },
                    { label: "2000+", val: 2050 },
                    { label: "5000+", val: 5050 },
                    { label: "10000+", val: 10050 },
                    { label: "30k+", val: 30050 }
                  ].map(opt => (
                    <label key={opt.val} className={`flex items-center space-x-1 px-2.5 py-1.5 border border-zinc-800 rounded bg-zinc-950/60 cursor-pointer hover:border-zinc-700 transition-colors ${customConnCount === opt.val ? "border-zinc-500 bg-zinc-900 text-white" : "text-zinc-500"}`}>
                      <input
                        type="radio"
                        name="connCountOverride"
                        checked={customConnCount === opt.val}
                        onChange={() => setCustomConnCount(opt.val)}
                        className="hidden"
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                  {customConnCount !== null && (
                    <button
                      type="button"
                      onClick={() => setCustomConnCount(null)}
                      className="text-[10px] text-rose-500 hover:underline px-2"
                    >
                      Clear Override
                    </button>
                  )}
                </div>
              </div>

              {/* Profile URL Input */}
              <div>
                <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">LinkedIn Profile URL</label>
                <input 
                  type="url" 
                  value={newConnUrl}
                  onChange={e => setNewConnUrl(e.target.value)}
                  placeholder="e.g. https://www.linkedin.com/in/username"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-700"
                />
              </div>

              {/* Profile Screenshot Input */}
              <div className="border border-dashed border-zinc-800 rounded-lg p-4 text-center bg-zinc-950/40 relative">
                <span className="text-xs text-zinc-400 block mb-2">Upload Profile Screenshot (Optional)</span>
                <input 
                  type="file" 
                  accept="image/*"
                  ref={screenshotInputRef}
                  onChange={(e) => setConnScreenshotFile(e.target.files?.[0] || null)}
                  className="hidden"
                />
                {connScreenshotFile ? (
                  <div className="text-xs text-emerald-400 font-mono flex items-center justify-center space-x-2">
                    <Check size={14} />
                    <span className="line-clamp-1">{connScreenshotFile.name}</span>
                    <button type="button" onClick={() => setConnScreenshotFile(null)} className="text-rose-500 hover:underline">Clear</button>
                  </div>
                ) : (
                  <button 
                    type="button"
                    onClick={() => screenshotInputRef.current?.click()}
                    className="text-xs bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-3 py-1.5 rounded text-zinc-300 hover:text-white transition-colors cursor-pointer"
                  >
                    Select Screenshot Image
                  </button>
                )}
                <span className="text-[9px] text-zinc-500 mt-1 block">Supports PNG, JPG, JPEG</span>
              </div>

              <div className="text-center text-[10px] text-zinc-500 font-mono uppercase tracking-wider">Or Input Manually</div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Full Name</label>
                  <input 
                    type="text" 
                    value={newConnName}
                    onChange={e => setNewConnName(e.target.value)}
                    required={connPdfFiles.length === 0}
                    disabled={connPdfFiles.length > 0}
                    placeholder="e.g. John Doe"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Current Title</label>
                  <input 
                    type="text" 
                    value={newConnTitle}
                    onChange={e => setNewConnTitle(e.target.value)}
                    disabled={connPdfFiles.length > 0}
                    placeholder="e.g. Staff Engineer"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Company</label>
                  <input 
                    type="text" 
                    value={newConnCompany}
                    onChange={e => setNewConnCompany(e.target.value)}
                    disabled={connPdfFiles.length > 0}
                    placeholder="e.g. Stripe"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Location</label>
                  <input 
                    type="text" 
                    value={newConnLocation}
                    onChange={e => setNewConnLocation(e.target.value)}
                    disabled={connPdfFiles.length > 0}
                    placeholder="e.g. San Francisco, CA"
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mb-1">Recent Posts Raw Text</label>
                <textarea 
                  value={newConnPosts}
                  onChange={e => setNewConnPosts(e.target.value)}
                  placeholder="Paste raw text copy-paste of their last 3 to 5 original posts..."
                  rows={3}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-200 focus:outline-none"
                />
              </div>

              <div className="flex justify-end items-center space-x-2 pt-2">
                <button 
                  type="button" 
                  onClick={() => setShowAddModal(false)}
                  className="bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-4 py-2 rounded-lg text-xs font-semibold text-zinc-300 hover:text-white transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={connUploadLoading}
                  className="bg-zinc-900 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-white hover:border-zinc-700 px-4 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50 shadow-lg shadow-zinc-950/40"
                >
                  {connUploadLoading ? "Processing..." : "Add to Queue"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
