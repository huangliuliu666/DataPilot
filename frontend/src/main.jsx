import React, { Component, memo, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Code2,
  Copy,
  Database,
  Download,
  Eye,
  FileText,
  Gauge,
  History,
  Home,
  KeyRound,
  Layers3,
  Loader2,
  Menu,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Table2,
  Trash2,
  UploadCloud,
  Wrench,
  X,
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      const detail = data.detail || data.message || data.error;
      if (typeof detail === 'string') message = detail;
      else if (detail) message = JSON.stringify(detail);
      else message = JSON.stringify(data);
    } catch (_) {
      try {
        const text = await res.text();
        if (text) message = text;
      } catch (_) {}
    }
    throw new Error(message);
  }
  const contentType = res.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) return {};
  return res.json();
}

function cn(...values) {
  return values.filter(Boolean).join(' ');
}

function normalizeError(error) {
  const msg = String(error?.message || error || '未知错误');
  if (/failed to fetch|networkerror|load failed|fetch resource/i.test(msg)) {
    return '无法连接后端服务。请确认 FastAPI 已启动，并检查 http://127.0.0.1:8000 是否可访问。';
  }
  return msg;
}

function Button({ children, variant = 'primary', size = 'md', loading = false, className = '', disabled, ...props }) {
  return (
    <button className={cn('btn', `btn-${variant}`, `btn-${size}`, className)} disabled={disabled || loading} {...props}>
      {loading ? <Loader2 size={16} className="spin" /> : null}
      {children}
    </button>
  );
}

function IconButton({ children, className = '', title, ...props }) {
  return <button className={cn('icon-btn', className)} title={title} {...props}>{children}</button>;
}

function Badge({ children, tone = 'neutral' }) {
  return <span className={cn('badge', `badge-${tone}`)}>{children}</span>;
}

function Field({ label, children, hint, required = false }) {
  return (
    <label className="field">
      <span className="field-label">{label}{required ? <b>*</b> : null}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

function Input(props) {
  return <input className="control input" {...props} />;
}

function Select(props) {
  return <select className="control select" {...props} />;
}

function TextArea(props) {
  return <textarea className="control textarea" {...props} />;
}

function Notice({ type = 'error', message, onClose }) {
  if (!message) return null;
  return (
    <div className={cn('notice', `notice-${type}`)}>
      <AlertCircle size={18} />
      <span>{message}</span>
      {onClose ? <IconButton onClick={onClose} title="关闭"><X size={15} /></IconButton> : null}
    </div>
  );
}

function Toast({ message, onClose }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onClose, 2600);
    return () => clearTimeout(timer);
  }, [message, onClose]);
  if (!message) return null;
  return <div className="toast"><CheckCircle2 size={18} />{message}</div>;
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('Front-end render error:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="fatal-screen">
          <div className="fatal-card">
            <h1>页面渲染异常</h1>
            <p>前端组件遇到异常，页面已停止渲染。请刷新页面；如果仍然出现，请把下面错误信息发给开发者。</p>
            <pre>{String(this.state.error?.message || this.state.error)}</pre>
            <button onClick={() => window.location.reload()}>刷新页面</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function Empty({ icon, title, desc }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      <div className="empty-desc">{desc}</div>
    </div>
  );
}

const CodeBlock = memo(function CodeBlock({ code, empty = '暂无内容', compact = false }) {
  return <pre className={cn('code-block', compact && 'code-compact')}><code>{code || empty}</code></pre>;
});

function SectionHeader({ eyebrow, title, desc, action }) {
  return (
    <div className="section-header">
      <div>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h2>{title}</h2>
        {desc ? <p>{desc}</p> : null}
      </div>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  );
}

function MetricCard({ icon, label, value, hint, tone = 'blue' }) {
  return (
    <div className="metric-card">
      <div className={cn('metric-icon', `metric-${tone}`)}>{icon}</div>
      <div className="metric-body">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value ?? '-'}</div>
        {hint ? <div className="metric-hint">{hint}</div> : null}
      </div>
    </div>
  );
}

function DataTable({ rows }) {
  const [expanded, setExpanded] = useState(false);
  if (!rows || rows.length === 0) {
    return <Empty icon={<Table2 size={22} />} title="没有返回数据" desc="SQL 执行成功，但结果为空。" />;
  }
  const columns = Object.keys(rows[0] || {});
  const visible = expanded ? rows : rows.slice(0, 5);
  return (
    <div className="data-table-card">
      <div className="table-toolbar">
        <span>{expanded ? `全部 ${rows.length} 行` : `预览前 ${Math.min(5, rows.length)} 行`}</span>
        {rows.length > 5 ? (
          <button className="link-button" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '收起结果' : '查看全部'}
          </button>
        ) : null}
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i}>{columns.map((c) => <td key={c}>{String(row[c] ?? '')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RecordCard({ record, type, onDelete }) {
  const isDoc = type === 'documentation';
  const isError = type === 'error_fix';
  const title = isDoc ? '业务文档' : isError ? record.question || '错误修复记录' : record.question || 'SQL 示例';
  const desc = isDoc ? '业务规则与指标口径' : isError ? '错误原因与修复建议' : '已确认的问题与 SQL';
  return (
    <div className="record-card">
      <div className="record-head">
        <div>
          <div className="record-title">{title}</div>
          <div className="record-desc">{desc}</div>
        </div>
        <IconButton onClick={() => onDelete(type, record.id)} title="删除"><Trash2 size={15} /></IconButton>
      </div>
      {isDoc ? <p className="record-text">{record.content}</p> : null}
      {!isDoc && !isError ? <CodeBlock code={record.sql} compact /> : null}
      {isError ? (
        <div className="error-memory">
          <p><b>错误信息：</b>{record.error_message}</p>
          <p><b>修复建议：</b>{record.fix_rule}</p>
          <CodeBlock code={record.wrong_sql} compact />
        </div>
      ) : null}
    </div>
  );
}

function SchemaViewerModal({ open, schemaPreview, onClose }) {
  const [tab, setTab] = useState('sql');
  if (!open) return null;
  const content = tab === 'sql'
    ? schemaPreview?.enriched_schema_sql
    : tab === 'markdown'
      ? schemaPreview?.enriched_schema_md
      : tab === 'manual'
        ? JSON.stringify(schemaPreview?.manual_annotations || {}, null, 2)
        : JSON.stringify(schemaPreview?.auto_annotations || {}, null, 2);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="schema-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="eyebrow">Schema Viewer</div>
            <h2>当前增强 Schema</h2>
            <p>这里展示最终用于 SQL 生成的结构化 schema 和注释。</p>
          </div>
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => navigator.clipboard.writeText(content || '')}><Copy size={15} />复制</Button>
            <IconButton onClick={onClose} title="关闭"><X size={18} /></IconButton>
          </div>
        </div>
        <div className="modal-tabs">
          <button className={cn(tab === 'sql' && 'active')} onClick={() => setTab('sql')}>SQL</button>
          <button className={cn(tab === 'markdown' && 'active')} onClick={() => setTab('markdown')}>Markdown</button>
          <button className={cn(tab === 'manual' && 'active')} onClick={() => setTab('manual')}>手写注释</button>
          <button className={cn(tab === 'auto' && 'active')} onClick={() => setTab('auto')}>自动注释</button>
        </div>
        <CodeBlock code={content} empty="暂无 schema。请先进入工作区或刷新 schema。" />
      </div>
    </div>
  );
}

function App() {
  const [page, setPage] = useState('overview');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [workspaces, setWorkspaces] = useState([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState('');
  const [activeDb, setActiveDb] = useState('');
  const [activeStatus, setActiveStatus] = useState(null);
  const [mysqlSessionPassword, setMysqlSessionPassword] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  const [connectType, setConnectType] = useState('MySQL');
  const [connectForm, setConnectForm] = useState({
    db_id: '', db_path: '', host: '127.0.0.1', port: 3306, user: 'root', password: '', database: '', charset: '', auto_train_schema: true, force_refresh: false,
  });
  const [connecting, setConnecting] = useState(false);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);

  const [records, setRecords] = useState({ documentation: [], question_sql: [], error_fix: [] });
  const [schemaPreview, setSchemaPreview] = useState(null);
  const [schemaModalOpen, setSchemaModalOpen] = useState(false);

  const [question, setQuestion] = useState('');
  const [evidence, setEvidence] = useState('');
  const [runSql, setRunSql] = useState(true);
  const [memoryTopK, setMemoryTopK] = useState(5);
  const [useTopology, setUseTopology] = useState(true);
  const [useGnn, setUseGnn] = useState(false);
  const [useGlobal, setUseGlobal] = useState(true);
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [resultTab, setResultTab] = useState('sql');
  const [showErrorForm, setShowErrorForm] = useState(false);
  const [answerError, setAnswerError] = useState({ error_message: '', fix_rule: '' });

  const [annotationText, setAnnotationText] = useState('');
  const [uploadedAnnotationName, setUploadedAnnotationName] = useState('');
  const [docText, setDocText] = useState('');
  const [example, setExample] = useState({ question: '', sql: '', evidence: '' });
  const [errorFix, setErrorFix] = useState({ question: '', wrong_sql: '', error_message: '', fix_rule: '' });

  const manifest = activeStatus?.manifest || {};
  const dbType = manifest.db_type || '';
  const canExecute = activeDb && (dbType === 'sqlite' || Boolean(mysqlSessionPassword));

  function showError(err) {
    setError(normalizeError(err));
  }

  async function refreshWorkspaces() {
    try {
      const data = await api('/workspaces');
      const list = data.workspaces || [];
      setWorkspaces(list);
      if (!selectedWorkspace && list.length) setSelectedWorkspace(list[0].db_id);
    } catch (err) {
      showError(err);
    }
  }

  async function loadRecords(dbId) {
    if (!dbId) return;
    const types = ['documentation', 'question_sql', 'error_fix'];
    const next = {};
    for (const t of types) {
      const data = await api(`/memory?db_id=${encodeURIComponent(dbId)}&record_type=${encodeURIComponent(t)}`);
      next[t] = data.records || [];
    }
    setRecords(next);
  }

  async function loadSchema(dbId) {
    if (!dbId) return;
    const data = await api(`/schema/${encodeURIComponent(dbId)}`);
    setSchemaPreview(data);
  }

  async function loadWorkspace(dbId = selectedWorkspace) {
    if (!dbId) return;
    setLoadingWorkspace(true);
    setError('');
    try {
      await api('/workspace/load', {
        method: 'POST',
        body: JSON.stringify({ db_id: dbId, mysql_password: mysqlSessionPassword || null }),
      });
      const status = await api(`/workspace/${encodeURIComponent(dbId)}`);
      setActiveDb(dbId);
      setActiveStatus(status);
      await loadRecords(dbId);
      await loadSchema(dbId);
      setPage('overview');
      setToast('工作区已进入');
    } catch (err) {
      showError(err);
    } finally {
      setLoadingWorkspace(false);
    }
  }

  async function connectDatabase() {
    if (!connectForm.db_id.trim()) return showError('请填写工作区名称。');
    setConnecting(true);
    setError('');
    try {
      const isMysql = connectType === 'MySQL';
      const path = isMysql ? '/connect/mysql' : '/connect/sqlite';
      const body = isMysql ? {
        db_id: connectForm.db_id.trim(),
        host: connectForm.host || '127.0.0.1',
        port: Number(connectForm.port || 3306),
        user: connectForm.user || 'root',
        password: connectForm.password || '',
        database: connectForm.database || '',
        charset: connectForm.charset || 'utf8mb4',
        auto_train_schema: connectForm.auto_train_schema,
        force_refresh: connectForm.force_refresh,
      } : {
        db_id: connectForm.db_id.trim(),
        db_path: connectForm.db_path || '',
        auto_train_schema: connectForm.auto_train_schema,
        force_refresh: connectForm.force_refresh,
      };
      await api(path, { method: 'POST', body: JSON.stringify(body) });
      await refreshWorkspaces();
      setSelectedWorkspace(connectForm.db_id.trim());
      if (isMysql) setMysqlSessionPassword(connectForm.password || mysqlSessionPassword);
      await loadWorkspace(connectForm.db_id.trim());
      setToast('数据源已连接');
    } catch (err) {
      showError(err);
    } finally {
      setConnecting(false);
    }
  }

  async function refreshSchema() {
    if (!activeDb) return;
    try {
      await api(`/refresh_schema/${encodeURIComponent(activeDb)}?auto_train_schema=true`, { method: 'POST' });
      const status = await api(`/workspace/${encodeURIComponent(activeDb)}`);
      setActiveStatus(status);
      await loadSchema(activeDb);
      setToast('Schema 已刷新');
    } catch (err) {
      showError(err);
    }
  }

  async function ask() {
    if (!activeDb) return showError('请先进入工作区。');
    if (!question.trim()) return showError('请输入业务问题。');
    setAsking(true);
    setError('');
    setAnswer(null);
    setResultTab('sql');
    try {
      const data = await api('/ask', {
        method: 'POST',
        body: JSON.stringify({
          db_id: activeDb,
          question,
          evidence,
          run_sql: runSql && canExecute,
          memory_top_k: Number(memoryTopK),
          use_topology_trimming: useTopology,
          use_sql_structure_retrieval: useGnn,
          use_global_structure_examples: useGlobal,
          result_limit: 100,
        }),
      });
      setAnswer(data);
      setToast('SQL 已生成');
    } catch (err) {
      showError(err);
    } finally {
      setAsking(false);
    }
  }

  async function importAnnotation() {
    if (!activeDb) return showError('请先进入工作区。');
    const text = annotationText || '';
    if (!text.trim()) return showError('请粘贴或上传注释内容。');
    try {
      await api('/import/annotated_schema', {
        method: 'POST',
        body: JSON.stringify({ db_id: activeDb, annotated_schema_text: text }),
      });
      setAnnotationText('');
      setUploadedAnnotationName('');
      await loadSchema(activeDb);
      const status = await api(`/workspace/${encodeURIComponent(activeDb)}`);
      setActiveStatus(status);
      setToast('注释已导入');
    } catch (err) {
      showError(err);
    }
  }

  async function readFile(file) {
    if (!file) return;
    const text = await file.text();
    setAnnotationText(text);
    setUploadedAnnotationName(file.name);
    setToast('文件内容已读取');
  }

  async function trainDoc() {
    if (!activeDb) return showError('请先进入工作区。');
    if (!docText.trim()) return showError('请输入业务文档。');
    try {
      await api('/train', { method: 'POST', body: JSON.stringify({ db_id: activeDb, documentation: docText, metadata: { source: 'web' } }) });
      setDocText('');
      await loadRecords(activeDb);
      setToast('业务文档已保存');
    } catch (err) {
      showError(err);
    }
  }

  async function trainExample() {
    if (!activeDb) return showError('请先进入工作区。');
    if (!example.question.trim() || !example.sql.trim()) return showError('问题和正确 SQL 不能为空。');
    try {
      await api('/train', { method: 'POST', body: JSON.stringify({ db_id: activeDb, question: example.question, sql: example.sql, metadata: { source: 'web', evidence: example.evidence } }) });
      setExample({ question: '', sql: '', evidence: '' });
      await loadRecords(activeDb);
      setToast('SQL 示例已保存');
    } catch (err) {
      showError(err);
    }
  }

  async function trainErrorFix(payload = errorFix) {
    if (!activeDb) return showError('请先进入工作区。');
    if (!payload.question?.trim() || !payload.wrong_sql?.trim() || !payload.error_message?.trim() || !payload.fix_rule?.trim()) {
      return showError('错误问题、错误 SQL、错误信息和修复建议都不能为空。');
    }
    try {
      await api('/train', {
        method: 'POST',
        body: JSON.stringify({ db_id: activeDb, question: payload.question, sql: payload.wrong_sql, error_message: payload.error_message, fix_rule: payload.fix_rule, metadata: { source: 'web_error_fix' } }),
      });
      setErrorFix({ question: '', wrong_sql: '', error_message: '', fix_rule: '' });
      setAnswerError({ error_message: '', fix_rule: '' });
      setShowErrorForm(false);
      await loadRecords(activeDb);
      setToast('错误修复已保存');
    } catch (err) {
      showError(err);
    }
  }

  async function saveAnswerAsExample() {
    if (!answer?.sql) return;
    try {
      await api('/train', { method: 'POST', body: JSON.stringify({ db_id: activeDb, question, sql: answer.sql, metadata: { source: 'user_confirmed', evidence } }) });
      await loadRecords(activeDb);
      setToast('已保存为历史示例');
    } catch (err) {
      showError(err);
    }
  }

  async function deleteRecord(type, id) {
    if (!activeDb || !id) return;
    try {
      await api(`/memory/${encodeURIComponent(activeDb)}/${encodeURIComponent(type)}/${encodeURIComponent(id)}`, { method: 'DELETE' });
      await loadRecords(activeDb);
      setToast('记录已删除');
    } catch (err) {
      showError(err);
    }
  }

  function copySql() {
    if (answer?.sql) navigator.clipboard.writeText(answer.sql);
    setToast('SQL 已复制');
  }

  function exportSql() {
    if (!answer?.sql) return;
    const blob = new Blob([answer.sql], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeDb || 'query'}.sql`;
    a.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => { refreshWorkspaces(); }, []);
  useEffect(() => {
    if (!error) return undefined;
    const timer = setTimeout(() => setError(''), 8000);
    return () => clearTimeout(timer);
  }, [error]);

  const counts = {
    tables: manifest.table_count || 0,
    columns: manifest.column_count || 0,
    docs: records.documentation.length,
    examples: records.question_sql.length,
    fixes: records.error_fix.length,
  };
  const selectedInfo = workspaces.find((w) => w.db_id === selectedWorkspace) || {};

  const navGroups = [
    { title: '工作区', items: [{ key: 'overview', icon: <Home size={18} />, label: '概览' }, { key: 'workspaces', icon: <ClipboardCheck size={18} />, label: '我的工作区' }, { key: 'connect', icon: <Plus size={18} />, label: '新建工作区' }] },
    { title: '数据管理', items: [{ key: 'datasource', icon: <Server size={18} />, label: '数据源连接' }, { key: 'schema', icon: <Table2 size={18} />, label: 'Schema 知识' }, { key: 'docs', icon: <FileText size={18} />, label: '业务文档' }, { key: 'examples', icon: <Code2 size={18} />, label: 'SQL 示例' }] },
    { title: '问答能力', items: [{ key: 'ask', icon: <MessageSquareText size={18} />, label: '自然语言查询' }, { key: 'history', icon: <History size={18} />, label: '查询历史' }, { key: 'errors', icon: <ShieldAlert size={18} />, label: '错误修复' }] },
    { title: '系统', items: [{ key: 'diagnostics', icon: <Gauge size={18} />, label: '运行诊断' }, { key: 'settings', icon: <Settings size={18} />, label: '系统设置' }] },
  ];

  return (
    <div className={cn('layout', !sidebarOpen && 'sidebar-collapsed')}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div><div className="brand-name">数据问答平台</div><div className="brand-sub">企业数据问答工作台</div></div>
        </div>
        <nav>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-title">{group.title}</div>
              {group.items.map((item) => (
                <button key={item.key} className={cn('nav-item', page === item.key && 'active')} onClick={() => setPage(item.key)}>
                  {item.icon}<span>{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <button className="collapse-note" onClick={() => setSidebarOpen(false)}><PanelLeftClose size={18} /> 收起侧边栏</button>
      </aside>
      {!sidebarOpen ? <button className="sidebar-restore" onClick={() => setSidebarOpen(true)}><PanelLeftOpen size={18} />菜单</button> : null}

      <main className="workspace">
        <header className="top-header">
          <div className="workspace-select-block">
            <label>当前工作区</label>
            <Select value={selectedWorkspace} onChange={(e) => setSelectedWorkspace(e.target.value)}>
              {workspaces.length ? workspaces.map((w) => <option key={w.db_id} value={w.db_id}>{w.db_id}</option>) : <option value="">暂无工作区</option>}
            </Select>
          </div>
          <div className="top-status"><label>数据源</label><b>{selectedInfo.db_type || dbType || '-'}</b><span>{selectedInfo.host || ''}{selectedInfo.port ? ` · ${selectedInfo.port}` : ''}</span></div>
          <div className="top-status"><label>Schema 状态</label><Badge tone={activeDb ? 'success' : 'neutral'}>{activeDb ? '已构建' : '未加载'}</Badge></div>
          <div className="top-status"><label>知识库状态</label><Badge tone={activeDb ? 'success' : 'neutral'}>{activeDb ? '可用' : '未加载'}</Badge></div>
          <div className="header-actions">
            <Button variant="ghost" onClick={() => loadWorkspace()} loading={loadingWorkspace}><RefreshCw size={16} />进入工作区</Button>
            <Button onClick={() => setPage('connect')}><Database size={16} />连接数据源</Button>
            <Button variant="ghost" onClick={() => { setPage('schema'); setSchemaModalOpen(true); }}><Eye size={16} />查看 Schema</Button>
            <IconButton><KeyRound size={18} /></IconButton>
            <div className="avatar">D</div>
          </div>
        </header>

        <div className="content">
          <Notice type="error" message={error} onClose={() => setError('')} />
          {page === 'overview' ? OverviewPage() : null}
          {page === 'ask' ? AskPage() : null}
          {page === 'connect' || page === 'datasource' ? ConnectPage() : null}
          {page === 'schema' ? SchemaPage() : null}
          {page === 'docs' ? DocsPage() : null}
          {page === 'examples' ? ExamplesPage() : null}
          {page === 'errors' ? ErrorsPage() : null}
          {page === 'workspaces' ? WorkspacesPage() : null}
          {page === 'diagnostics' ? DiagnosticsPage() : null}
          {page === 'settings' || page === 'history' ? PlaceholderPage({ title: page === 'history' ? '查询历史' : '系统设置' }) : null}
        </div>
      </main>
      <SchemaViewerModal open={schemaModalOpen} schemaPreview={schemaPreview} onClose={() => setSchemaModalOpen(false)} />
      <Toast message={toast} onClose={() => setToast('')} />
    </div>
  );

  function OverviewPage() {
    return (
      <>
        <section className="hero">
          <div>
            <div className="hero-kicker">DATA QUERY WORKSPACE</div>
            <h1>企业数据问答工作台</h1>
            <p>统一管理数据源、业务口径与历史 SQL 示例，让业务人员用自然语言获得可验证的查询结果。</p>
          </div>
          <div className="hero-actions"><Badge tone={canExecute ? 'success' : 'warning'}>{canExecute ? '可执行 SQL' : '仅生成 SQL'}</Badge><Badge tone="info">当前：{activeDb || '未进入工作区'}</Badge></div>
        </section>
        <section className="metric-grid">
          <MetricCard icon={<Home size={24} />} label="当前工作区" value={activeDb || '未进入'} hint="正在操作的知识库" tone="blue" />
          <MetricCard icon={<Database size={24} />} label="数据源" value={dbType || '-'} hint={activeDb ? '已连接' : '未加载'} tone="blue" />
          <MetricCard icon={<Table2 size={24} />} label="表数量" value={counts.tables} hint="当前工作区" tone="green" />
          <MetricCard icon={<Layers3 size={24} />} label="字段数量" value={counts.columns} hint="Schema 字段" tone="purple" />
          <MetricCard icon={<FileText size={24} />} label="业务文档" value={counts.docs} hint="参与召回" tone="orange" />
          <MetricCard icon={<Code2 size={24} />} label="SQL 示例" value={counts.examples} hint="历史示例" tone="blue" />
          <MetricCard icon={<ShieldCheck size={24} />} label="错误修复" value={counts.fixes} hint="提升准确性" tone="red" />
        </section>
        {AskPage({ compact: true })}
      </>
    );
  }

  function AskPage(props = {}) {
  const { compact = false } = props;

  return (
    <section className="ask-grid">
      <div className="ask-main panel emphasis-panel">
        <div className="ask-title-row">
          <SectionHeader
            eyebrow="Natural Language Query"
            title="自然语言查询"
            desc="输入业务问题，系统会检索当前工作区的 schema、业务文档、历史示例和列值提示，然后生成 SQL。"
          />
          <button
            className="use-example"
            onClick={() => setQuestion('查询有哪些自行车品牌？')}
          >
            <Search size={15} /> 使用示例
          </button>
        </div>

        <Field label="业务问题" required>
          <TextArea
            rows={compact ? 4 : 6}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：统计各地区近三个月销售额最高的前 10 个客户"
            maxLength={1000}
          />
        </Field>

        <Field label="补充说明（可选）">
          <TextArea
            rows={3}
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
            placeholder="可填写指标口径、筛选条件或业务规则"
            maxLength={500}
          />
        </Field>

        <div className="query-options">
          <label>
            <input
              type="checkbox"
              checked={runSql}
              onChange={(e) => setRunSql(e.target.checked)}
            />
            生成后执行 SQL
          </label>

          <label>
            <input
              type="checkbox"
              checked={useTopology}
              onChange={(e) => setUseTopology(e.target.checked)}
            />
            使用精简 Schema
          </label>

          <label>
            <input
              type="checkbox"
              checked={useGnn}
              onChange={(e) => setUseGnn(e.target.checked)}
            />
            使用结构相似示例
          </label>

          <label>
            <input
              type="checkbox"
              checked={useGlobal}
              onChange={(e) => setUseGlobal(e.target.checked)}
            />
            使用通用查询模式
          </label>

          <label className="inline-number">
            最多示例
            <Input
              type="number"
              min="1"
              max="10"
              value={memoryTopK}
              onChange={(e) => setMemoryTopK(e.target.value)}
            />
          </label>
        </div>

        <div className="ask-actions">
          <Button onClick={ask} loading={asking} className="ask-primary">
            <Play size={16} />
            {runSql && canExecute ? '生成并执行' : '生成 SQL'}
          </Button>

          <Button
            variant="ghost"
            onClick={() => {
              setQuestion('');
              setEvidence('');
            }}
          >
            清空输入
          </Button>
        </div>
      </div>

      <aside className="context-panel panel">
        <SectionHeader title="当前上下文" desc="本次查询可用的知识范围。" />

        <ContextItem
          icon={<Database size={16} />}
          label="数据源"
          value={activeDb ? '已连接' : '未进入'}
        />

        <ContextItem
          icon={<Table2 size={16} />}
          label="Schema"
          value={activeDb ? `${counts.tables} 表 · ${counts.columns} 字段` : '未加载'}
          link="查看"
          onClick={() => setSchemaModalOpen(true)}
        />

        <ContextItem
          icon={<FileText size={16} />}
          label="业务文档"
          value={`${counts.docs} 份`}
          link="管理"
          onClick={() => setPage('docs')}
        />

        <ContextItem
          icon={<Code2 size={16} />}
          label="SQL 示例"
          value={`${counts.examples} 条`}
          link="查看"
          onClick={() => setPage('examples')}
        />

        <ContextItem
          icon={<ShieldCheck size={16} />}
          label="错误修复"
          value={`${counts.fixes} 条`}
          link="查看"
          onClick={() => setPage('errors')}
        />
      </aside>

      {asking ? (
        <section className="result-section full-row">
          {Progress()}
        </section>
      ) : null}

      {answer ? ResultSection() : null}
    </section>
  );
}

  function ConnectPage() {
    return (
      <section className="panel form-panel">
        <SectionHeader title="连接数据源" desc="创建新的数据库工作区，系统会自动读取 schema、生成初始注释并保存到本地。" />
        <div className="form-grid two-col">
          <Field label="数据库类型"><Select value={connectType} onChange={(e) => setConnectType(e.target.value)}><option>MySQL</option><option>SQLite</option></Select></Field>
          <Field label="工作区名称"><Input value={connectForm.db_id} onChange={(e) => setConnectForm({ ...connectForm, db_id: e.target.value })} placeholder="例如：sales_prod" /></Field>
          {connectType === 'SQLite' ? (
            <Field label="SQLite 文件路径"><Input value={connectForm.db_path} onChange={(e) => setConnectForm({ ...connectForm, db_path: e.target.value })} placeholder="/path/to/database.sqlite" /></Field>
          ) : (
            <>
              <Field label="Host"><Input value={connectForm.host} onChange={(e) => setConnectForm({ ...connectForm, host: e.target.value })} /></Field>
              <Field label="Port"><Input value={connectForm.port} onChange={(e) => setConnectForm({ ...connectForm, port: e.target.value })} /></Field>
              <Field label="User"><Input value={connectForm.user} onChange={(e) => setConnectForm({ ...connectForm, user: e.target.value })} /></Field>
              <Field label="Password"><Input type="password" value={connectForm.password} onChange={(e) => setConnectForm({ ...connectForm, password: e.target.value })} /></Field>
              <Field label="Database"><Input value={connectForm.database} onChange={(e) => setConnectForm({ ...connectForm, database: e.target.value })} placeholder="数据库名" /></Field>
              <Field label="Charset"><Input value={connectForm.charset} onChange={(e) => setConnectForm({ ...connectForm, charset: e.target.value })} placeholder="留空使用默认字符集" /></Field>
            </>
          )}
        </div>
        <div className="form-checks"><label><input type="checkbox" checked={connectForm.auto_train_schema} onChange={(e) => setConnectForm({ ...connectForm, auto_train_schema: e.target.checked })} />自动构建 Schema 工作区</label><label><input type="checkbox" checked={connectForm.force_refresh} onChange={(e) => setConnectForm({ ...connectForm, force_refresh: e.target.checked })} />重新读取 Schema 和注释</label></div>
        <Button onClick={connectDatabase} loading={connecting}>连接并进入工作区</Button>
      </section>
    );
  }

  function SchemaPage() {
    return (
      <section className="schema-workspace">
        <div className="panel schema-import-panel">
          <SectionHeader title="导入表/字段注释" desc="支持 SQL DDL COMMENT、普通文本和 JSON。手写注释会优先于自动注释。" />
          <label className="upload-box"><UploadCloud size={18} /> 上传 .sql / .txt / .md / .json 文件<input type="file" accept=".sql,.txt,.md,.json" onChange={(e) => readFile(e.target.files?.[0])} /></label>
          {uploadedAnnotationName ? <div className="file-chip">已读取：{uploadedAnnotationName}</div> : null}
          <textarea className="control textarea schema-input" value={annotationText} onChange={(e) => setAnnotationText(e.target.value)} placeholder="CREATE TABLE ... COMMENT '...';" />
          <div className="button-row"><Button onClick={importAnnotation}>导入注释</Button><Button variant="ghost" onClick={() => { setAnnotationText(''); setUploadedAnnotationName(''); }}>清空</Button></div>
        </div>
        <div className="panel schema-summary-panel">
          <SectionHeader title="当前增强 Schema" desc="查看最终用于 SQL 生成的 schema、手写注释和自动注释。" action={<Button variant="ghost" onClick={() => loadSchema(activeDb)}><RefreshCw size={16} />刷新</Button>} />
          <div className="schema-stat-grid">
            <div><b>{counts.tables}</b><span>表</span></div>
            <div><b>{counts.columns}</b><span>字段</span></div>
            <div><b>{activeStatus?.manual_table_annotations + activeStatus?.manual_column_annotations || 0}</b><span>手写注释</span></div>
          </div>
          <Button onClick={() => setSchemaModalOpen(true)}><Eye size={16} />打开 Schema 查看器</Button>
          <p className="muted-text">Schema 内容较大时建议在查看器中阅读、搜索或复制，避免影响输入区域。</p>
        </div>
      </section>
    );
  }

  function DocsPage() {
    return (
      <section className="panel">
        <SectionHeader title="业务文档" desc="保存指标公式、业务规则、同义词和默认过滤条件。" />
        <TextArea rows={7} value={docText} onChange={(e) => setDocText(e.target.value)} placeholder="例如：GMV = SUM(quantity * price * (1 - discount))" />
        <div className="button-row"><Button onClick={trainDoc}>保存业务文档</Button><Button variant="ghost" onClick={() => setDocText('')}>清空</Button></div>
        <RecordList type="documentation" records={records.documentation} />
      </section>
    );
  }

  function ExamplesPage() {
    return (
      <section className="panel">
        <SectionHeader title="SQL 示例" desc="保存经过确认的问题和正确 SQL，供后续相似问题复用。" />
        <div className="form-grid">
          <TextArea rows={3} value={example.question} onChange={(e) => setExample({ ...example, question: e.target.value })} placeholder="问题" />
          <TextArea rows={7} value={example.sql} onChange={(e) => setExample({ ...example, sql: e.target.value })} placeholder="正确 SQL" />
          <TextArea rows={2} value={example.evidence} onChange={(e) => setExample({ ...example, evidence: e.target.value })} placeholder="说明（可选）" />
        </div>
        <div className="button-row"><Button onClick={trainExample}>保存示例</Button><Button variant="ghost" onClick={() => setExample({ question: '', sql: '', evidence: '' })}>清空</Button></div>
        <RecordList type="question_sql" records={records.question_sql} />
      </section>
    );
  }

  function ErrorsPage() {
    return (
      <section className="panel">
        <SectionHeader title="错误修复" desc="记录错误 SQL、错误原因和修复建议，用于后续生成前规避类似问题。" />
        <div className="form-grid">
          <TextArea rows={2} value={errorFix.question} onChange={(e) => setErrorFix({ ...errorFix, question: e.target.value })} placeholder="错误问题" />
          <TextArea rows={6} value={errorFix.wrong_sql} onChange={(e) => setErrorFix({ ...errorFix, wrong_sql: e.target.value })} placeholder="错误 SQL" />
          <TextArea rows={2} value={errorFix.error_message} onChange={(e) => setErrorFix({ ...errorFix, error_message: e.target.value })} placeholder="错误信息" />
          <TextArea rows={2} value={errorFix.fix_rule} onChange={(e) => setErrorFix({ ...errorFix, fix_rule: e.target.value })} placeholder="修复建议" />
        </div>
        <div className="button-row"><Button onClick={() => trainErrorFix()}>保存错误修复</Button><Button variant="ghost" onClick={() => setErrorFix({ question: '', wrong_sql: '', error_message: '', fix_rule: '' })}>清空</Button></div>
        <RecordList type="error_fix" records={records.error_fix} />
      </section>
    );
  }

  function WorkspacesPage() {
    return (
      <section className="panel">
        <SectionHeader title="我的工作区" desc="选择已处理过的数据源并进入工作区。" />
        <div className="workspace-list">
          {workspaces.map((w) => <button key={w.db_id} className={cn('workspace-card', selectedWorkspace === w.db_id && 'selected')} onClick={() => setSelectedWorkspace(w.db_id)}><b>{w.db_id}</b><span>{w.db_type || 'database'}</span></button>)}
        </div>
        <Button onClick={() => loadWorkspace()} loading={loadingWorkspace}>进入所选工作区</Button>
      </section>
    );
  }

  function DiagnosticsPage() {
    return (
      <section className="diagnostics-grid">
        <div className="panel"><SectionHeader title="运行状态" desc="用于排查连接和工作区状态。" /><CodeBlock code={JSON.stringify(activeStatus || {}, null, 2)} /></div>
        <div className="panel"><SectionHeader title="系统信息" desc="当前前后端连接信息。" /><div className="diagnostic-list"><p>后端地址：{API_BASE}</p><p>当前工作区：{activeDb || '未进入'}</p><p>执行能力：{canExecute ? '可执行 SQL' : '仅生成 SQL'}</p></div></div>
      </section>
    );
  }

  function PlaceholderPage({ title }) {
    return <section className="panel"><SectionHeader title={title} desc="该模块正在规划中。" /></section>;
  }

  function ContextItem({ icon, label, value, link, onClick }) {
    return <div className="context-item"><div>{icon}<span>{label}</span></div><b>{value}</b>{link ? <button onClick={onClick}>{link}</button> : null}</div>;
  }

  function RecordList({ type, records }) {
    return (
      <div className="record-list">
        {records?.length ? records.slice().reverse().map((r) => <RecordCard key={r.id} record={r} type={type} onDelete={deleteRecord} />) : <Empty icon={<BookOpen size={22} />} title="暂无记录" desc="保存后会显示在这里。" />}
      </div>
    );
  }

  function ResultSection() {
    return (
      <section className="result-section full-row">
        <div className="result-head"><div><div className="eyebrow">Generated SQL</div><h2>生成结果</h2></div><div className="button-row"><Button variant="ghost" onClick={copySql}><Copy size={16} />复制 SQL</Button><Button variant="ghost" onClick={exportSql}><Download size={16} />导出 SQL</Button><Button onClick={saveAnswerAsExample}><CheckCircle2 size={16} />确认正确并保存</Button><Button variant="secondary" onClick={() => setShowErrorForm((v) => !v)}><AlertCircle size={16} />记录为错误</Button></div></div>
        <div className="result-tabs"><button className={cn(resultTab === 'sql' && 'active')} onClick={() => setResultTab('sql')}>SQL</button><button className={cn(resultTab === 'result' && 'active')} onClick={() => setResultTab('result')}>查询结果</button><button className={cn(resultTab === 'knowledge' && 'active')} onClick={() => setResultTab('knowledge')}>使用的知识</button></div>
        {resultTab === 'sql' ? <CodeBlock code={answer.sql} /> : null}
        {resultTab === 'result' ? <DataTable rows={answer.result || []} /> : null}
        {resultTab === 'knowledge' ? <div className="details-grid"><details open><summary>Schema / 注释</summary><pre>{answer.used_schema || '暂无'}</pre></details><details><summary>示例召回</summary><pre>{answer.examples_used || '本次没有匹配到示例。'}</pre></details><details><summary>业务文档</summary><pre>{answer.memory_documentation || '本次没有匹配到业务文档。'}</pre></details><details><summary>列值提示</summary><pre>{answer.column_value_hints || '本次没有列值提示。'}</pre></details></div> : null}
        {showErrorForm ? <div className="error-report"><h3>记录本次 SQL 的错误原因和修复建议</h3><TextArea rows={2} value={answerError.error_message} onChange={(e) => setAnswerError({ ...answerError, error_message: e.target.value })} placeholder="错误原因" /><TextArea rows={2} value={answerError.fix_rule} onChange={(e) => setAnswerError({ ...answerError, fix_rule: e.target.value })} placeholder="修复建议" /><div className="button-row"><Button onClick={() => trainErrorFix({ question, wrong_sql: answer.sql, error_message: answerError.error_message, fix_rule: answerError.fix_rule })}>保存错误修复</Button><Button variant="ghost" onClick={() => setShowErrorForm(false)}>取消</Button></div></div> : null}
      </section>
    );
  }

  function Progress() {
    return <div className="progress-card"><Loader2 className="spin" size={24} /><div><b>正在生成 SQL</b><p>系统正在检索 schema、业务文档和历史示例，请稍候。</p></div></div>;
  }
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>);
