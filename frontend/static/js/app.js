const state = {
	user: null,
	role: null,
	modelReady: false,
	modelProgress: 0,
	currentView: 'login'
};

const dom = {
	app: document.getElementById('app'),
	views: {
		login: document.getElementById('view-login'),
		student: document.getElementById('view-student'),
		professor: document.getElementById('view-professor')
	},
	auth: {
		loginForm: document.getElementById('login-form'),
		registerForm: document.getElementById('register-form'),
		error: document.getElementById('auth-error'),
		tabs: document.querySelectorAll('.auth-card .tab-btn')
	},
	nav: {
		bar: document.getElementById('navbar'),
		user: document.getElementById('user-display'),
		logout: document.getElementById('logout-btn'),
		themeToggle: document.getElementById('theme-toggle')
	},
	student: {
		statusCard: document.getElementById('model-status-card'),
		statusText: document.getElementById('status-text'),
		progressBar: document.getElementById('model-progress'),
		progressContainer: document.querySelector('.progress-bar-container'),
		fileInput: document.getElementById('file-input'),
		dropZone: document.getElementById('drop-zone'),
		preview: document.getElementById('upload-preview'),
		fileName: document.getElementById('file-name'),
		cancelBtn: document.getElementById('cancel-upload'),
		processBtn: document.getElementById('process-btn'),
		processBtnTxt: document.getElementById('process-text-btn'),
		textInput: document.getElementById('text-input'),
		results: document.getElementById('analysis-results'),
		resultTabs: document.querySelectorAll('.result-tabs .tab-btn'),
		usageChartCtx: document.getElementById('studentUsageChart'),
		historyList: document.getElementById('history-list')
	},
	prof: {
		refreshBtn: document.getElementById('refresh-prof-btn'),
		tableBody: document.querySelector('#students-table tbody'),
		kpis: {
			students: document.getElementById('prof-total-students'),
			docs: document.getElementById('prof-total-docs'),
			errors: document.getElementById('prof-avg-errors')
		},
		chartCtx: document.getElementById('classMetricsChart'),
		docsContainer: document.getElementById('student-docs-container'),
		docsList: document.getElementById('student-docs-list'),
		selectedStudentName: document.getElementById('selected-student-name')
	}
};

let metricsChart = null;
let statusInterval = null;

// --- INITIALIZATION ---
async function init() {
	initTheme();
	setupEventListeners();
	checkSession();
	startStatusPolling();
}

function initTheme() {
	const savedTheme = localStorage.getItem('palabria_theme') || 'light';
	document.documentElement.setAttribute('data-theme', savedTheme);
	updateThemeIcon(savedTheme);
}

function toggleTheme() {
	const current = document.documentElement.getAttribute('data-theme');
	const next = current === 'light' ? 'dark' : 'light';
	document.documentElement.setAttribute('data-theme', next);
	localStorage.setItem('palabria_theme', next);
	updateThemeIcon(next);
}

function updateThemeIcon(theme) {
	// Simple SVG swap or class toggle
	const btn = dom.nav.themeToggle;
	if (theme === 'dark') {
		btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-sun"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
	} else {
		btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-moon"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
	}
}

function setupEventListeners() {
	// Theme
	if (dom.nav.themeToggle) {
		dom.nav.themeToggle.addEventListener('click', toggleTheme);
	}

	// Auth Tabs
	dom.auth.tabs.forEach(btn => {
		btn.addEventListener('click', (e) => {
			// 1. Update Tab Buttons
			dom.auth.tabs.forEach(b => b.classList.remove('active'));
			e.target.classList.add('active');

			// 2. Show Target Form
			const targetId = e.target.dataset.target;
			const loginForm = document.getElementById('login-form');
			const registerForm = document.getElementById('register-form');

			// Reset all forms
			loginForm.classList.remove('active');
			registerForm.classList.remove('active');

			// Activate target
			document.getElementById(targetId).classList.add('active');

			// 3. Clear Errors
			dom.auth.error.classList.add('hidden');
		});
	});

	// Forms
	dom.auth.loginForm.addEventListener('submit', handleLogin);
	dom.auth.registerForm.addEventListener('submit', handleRegister);
	dom.nav.logout.addEventListener('click', handleLogout);

	// Student Upload
	dom.student.dropZone.addEventListener('click', () => dom.student.fileInput.click());
	dom.student.dropZone.addEventListener('dragover', (e) => {
		e.preventDefault();
		dom.student.dropZone.classList.add('dragover');
	});
	dom.student.dropZone.addEventListener('dragleave', () => dom.student.dropZone.classList.remove('dragover'));
	dom.student.dropZone.addEventListener('drop', (e) => {
		e.preventDefault();
		dom.student.dropZone.classList.remove('dragover');
		handleFileSelect(e.dataTransfer.files[0]);
	});
	dom.student.fileInput.addEventListener('change', (e) => handleFileSelect(e.target.files[0]));
	dom.student.cancelBtn.addEventListener('click', clearFileSelection);
	dom.student.processBtn.addEventListener('click', processFile);

	// Text input processing
	if (dom.student.processBtnTxt) {
		dom.student.processBtnTxt.addEventListener('click', processText);
	}

	if (dom.student.textInput) {
		// Enable/disable analyze button depending on content
		dom.student.textInput.addEventListener('input', (e) => {
			const hasText = e.target.value && e.target.value.trim().length > 0;
			dom.student.processBtnTxt.disabled = !hasText;
		});
		// initialize state
		dom.student.processBtnTxt.disabled = !(dom.student.textInput.value && dom.student.textInput.value.trim().length > 0);
	}

	// Results Tabs
	dom.student.resultTabs.forEach(btn => {
		btn.addEventListener('click', (e) => {
			dom.student.resultTabs.forEach(b => b.classList.remove('active'));
			e.target.classList.add('active');

			const target = e.target.dataset.target;
			document.querySelectorAll('.tab-content').forEach(c => {
				c.classList.remove('active');
				if (c.id === target) c.classList.add('active');
			});
		});
	});

	// Prof
	dom.prof.refreshBtn.addEventListener('click', loadProfessorData);
}

// --- AUTH LOGIC ---
function checkSession() {
	const user = localStorage.getItem('palabria_user');
	const role = localStorage.getItem('palabria_role');
	if (user) {
		state.user = user;
		state.role = role || 'student';
		showView(state.role === 'professor' ? 'professor' : 'student');
	} else {
		showView('login');
	}
}

async function handleLogin(e) {
	e.preventDefault();
	const username = document.getElementById('login-username').value;

	showLoader(true);
	try {
		const fd = new FormData();
		fd.append('username', username);
		const res = await fetch('/users/login', { method: 'POST', body: fd });
		const data = await res.json();

		if (data.ok) {
			loginSuccess(data.username, data.role);
		} else {
			showAuthError(data.detail || 'Error en login');
		}
	} catch (err) {
		showAuthError('Error de conexión');
	} finally {
		showLoader(false);
	}
}

async function handleRegister(e) {
	e.preventDefault();
	const username = document.getElementById('reg-username').value;
	const role = document.querySelector('input[name="role"]:checked').value;

	showLoader(true);
	try {
		const fd = new FormData();
		fd.append('username', username);
		fd.append('role', role);
		const res = await fetch('/users/create', { method: 'POST', body: fd });
		const data = await res.json();

		if (data.ok) {
			loginSuccess(data.username, data.role);
		} else {
			showAuthError(data.detail || 'Error al crear cuenta');
		}
	} catch (err) {
		showAuthError('Error de conexión');
	} finally {
		showLoader(false);
	}
}

function loginSuccess(user, role) {
	state.user = user;
	state.role = role;
	localStorage.setItem('palabria_user', user);
	localStorage.setItem('palabria_role', role);

	// Trigger backend load if student
	if (role === 'student') {
		fetch('/load/', { method: 'POST' }).catch(() => { });
	}

	showView(role === 'professor' ? 'professor' : 'student');
}

async function handleLogout() {
	if (state.user) {
		const fd = new FormData();
		fd.append('username', state.user);
		await fetch('/users/logout', { method: 'POST', body: fd }).catch(() => { });
	}
	state.user = null;
	state.role = null;
	localStorage.removeItem('palabria_user');
	localStorage.removeItem('palabria_role');
	showView('login');
}

function showAuthError(msg) {
	dom.auth.error.textContent = msg;
	dom.auth.error.classList.remove('hidden');
}

// --- ROUTING / VIEW MGT ---
function showView(viewName) {
	// Hide all
	Object.values(dom.views).forEach(el => {
		el.classList.add('hidden');
		el.classList.remove('active');
	});

	// Show target
	dom.views[viewName].classList.remove('hidden');
	dom.views[viewName].classList.add('active');
	state.currentView = viewName;

	// Navbar
	if (viewName === 'login') {
		dom.nav.bar.style.display = 'none';
	} else {
		dom.nav.bar.style.display = 'flex';
		dom.nav.user.textContent = `${state.user} (${state.role === 'student' ? 'Estudiante' : 'Profesor'})`;
	}

	// Init View Data
	if (viewName === 'professor') {
		loadProfessorData();
	}
	if (viewName === 'student') {
		loadStudentHistory();
	}
}

// Cargar historial de análisis del estudiante
async function loadStudentHistory() {
	try {
		const res = await fetch(`/users/${state.user}/documents`);
		const data = await res.json();
		
		const historyList = document.getElementById('history-list');
		if (!historyList) return;
		
		if (data.documents && data.documents.length > 0) {
			const historyHtml = data.documents.map(doc => `
				<div class="history-item" onclick="loadDocument(${doc.id})">
					<span class="history-name">${doc.filename}</span>
					<span class="history-date">${new Date(doc.uploaded_at).toLocaleDateString('es-ES')}</span>
				</div>
			`).join('');
			
			historyList.innerHTML = historyHtml;
		} else {
			historyList.innerHTML = '<p class="text-muted">No hay análisis anteriores</p>';
		}
	} catch (err) {
		console.warn('No se pudo cargar historial:', err);
		const historyList = document.getElementById('history-list');
		if (historyList) {
			historyList.innerHTML = '<p class="text-muted">Error al cargar historial</p>';
		}
	}
}

// Cargar documento del historial
async function loadDocument(docId) {
	showLoader(true);
	try {
		const res = await fetch(`/documents/${docId}`);
		const data = await res.json();
		
		if (data.doc_id) {
			renderResults(data);
		}
	} catch (err) {
		console.error('Error cargando documento:', err);
		alert('No se pudo cargar el documento');
	} finally {
		showLoader(false);
	}
}

// --- STUDENT LOGIC ---
let selectedFile = null;

function handleFileSelect(file) {
	if (!file || file.type !== 'application/pdf') {
		alert('Por favor selecciona un archivo PDF válido.');
		return;
	}
	selectedFile = file;
	dom.student.fileName.textContent = file.name;
	dom.student.dropZone.classList.add('hidden');
	dom.student.preview.classList.remove('hidden');
	dom.student.processBtn.disabled = false;
	dom.student.resultTabs[0].click(); // Reset tab
}

function clearFileSelection() {
	selectedFile = null;
	dom.student.fileInput.value = '';
	dom.student.dropZone.classList.remove('hidden');
	dom.student.preview.classList.add('hidden');
	dom.student.processBtn.disabled = true;
	dom.student.results.classList.add('hidden');
}

async function processFile() {
	if (!selectedFile) return;

	showLoader(true);
	try {
		const fd = new FormData();
		fd.append('file', selectedFile);
		fd.append('username', state.user);

		const res = await fetch('/process/', { method: 'POST', body: fd });
		
		if (!res.ok) {
			const errorData = await res.json().catch(() => ({}));
			console.error('Error del servidor:', res.status, errorData);
			alert(`Error al procesar el archivo (${res.status}): ${errorData.detail || 'Error desconocido'}`);
			return;
		}
		
		const data = await res.json();

		if (data.doc_id) {
			renderResults(data);
			clearFileSelection();
		} else {
			console.error('Respuesta sin doc_id:', data);
			alert('Error al procesar el archivo: respuesta inválida del servidor.');
		}
	} catch (err) {
		console.error('Error en processFile:', err);
		alert('Error conectando con el servidor: ' + err.message);
	} finally {
		showLoader(false);
	}
}

async function processText() {
	const text = dom.student.textInput ? dom.student.textInput.value : '';
	if (!text || !text.trim()) return;

	if (!state.user) {
		alert('Inicia sesión para enviar texto a corrección.');
		return;
	}

	showLoader(true);
	try {
		const fd = new FormData();
		fd.append('username', state.user);
		fd.append('text', text);

		const res = await fetch('/process_text/', { method: 'POST', body: fd });
		
		if (!res.ok) {
			const errorData = await res.json().catch(() => ({}));
			console.error('Error del servidor:', res.status, errorData);
			alert(`Error al procesar el texto (${res.status}): ${errorData.detail || 'Error desconocido'}`);
			return;
		}
		
		const data = await res.json();

		if (data.doc_id) {
			renderResults(data);
			// Limpiar input después de procesar exitosamente
			dom.student.textInput.value = '';
			dom.student.processBtnTxt.disabled = true;
		} else {
			console.error('Respuesta sin doc_id:', data);
			alert('Error al procesar el texto: respuesta inválida del servidor.');
		}
	} catch (err) {
		console.error('Error en processText:', err);
		alert('Error conectando con el servidor: ' + err.message);
	} finally {
		showLoader(false);
	}
}

function renderResults(data) {
	dom.student.results.classList.remove('hidden');

	// KPIs
	document.getElementById('kpi-sentences').textContent = data.metricas.total_frases;
	document.getElementById('kpi-errors').textContent = data.metricas.frases_con_tu_impersonal;
	document.getElementById('kpi-changes').textContent = data.metricas.cambios_propuestos_modelo;

	// Content
	document.getElementById('tab-feedback').innerHTML = formatFeedback(data.feedback);
	document.getElementById('tab-corrected').textContent = data.corrected;
	document.getElementById('tab-original').textContent = data.original_text;

	// Asegurar que el primer tab (feedback) esté activo
	dom.student.resultTabs.forEach((btn, idx) => {
		if (idx === 0) {
			btn.classList.add('active');
		} else {
			btn.classList.remove('active');
		}
	});

	// Asegurar que solo tab-feedback esté visible
	document.querySelectorAll('.tab-content').forEach(tab => {
		if (tab.id === 'tab-feedback') {
			tab.classList.add('active');
		} else {
			tab.classList.remove('active');
		}
	});
}

function formatFeedback(text) {
	// Simple markdown-like formatting for better reading
	return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
		.replace(/\n/g, '<br>');
}

// --- PROFESSOR LOGIC ---
async function loadProfessorData() {
	showLoader(true, false); // Light loader
	try {
		const res = await fetch('/professor/overview');
		const data = await res.json();

		// KPIs
		dom.prof.kpis.students.textContent = data.total_students;
		dom.prof.kpis.docs.textContent = data.total_docs;
		dom.prof.kpis.errors.textContent = (data.avg_metrics.frases_con_tu_impersonal || 0).toFixed(1);

		// Chart
		renderClassChart(data.avg_metrics);

		// Table
		const rows = data.students.map(s => `
            <tr onclick="loadStudentDocuments('${s.username}')" style="cursor:pointer;">
                <td>${s.username}</td>
                <td>${s.docs_count}</td>
                <td>${s.last_upload || 'Nunca'}</td>
            </tr>
        `).join('');
		dom.prof.tableBody.innerHTML = rows || '<tr><td colspan="3" class="text-center">No hay alumnos.</td></tr>';

	} catch (err) {
		console.error(err);
	} finally {
		showLoader(false);
	}
}

function renderClassChart(metrics) {
	const ctx = dom.prof.chartCtx.getContext('2d');

	if (metricsChart) metricsChart.destroy();

	const labels = ["Total Frases", "Errores 'Tú'", "Cambios Realizados"];
	const values = [
		metrics.total_frases || 0,
		metrics.frases_con_tu_impersonal || 0,
		metrics.cambios_realizados_usuario || 0
	];

	metricsChart = new Chart(ctx, {
		type: 'bar',
		data: {
			labels: labels,
			datasets: [{
				label: 'Promedio de Clase',
				data: values,
				backgroundColor: ['#3b82f6', '#ef4444', '#22c55e'],
				borderRadius: 4
			}]
		},
		options: {
			responsive: true,
			plugins: { legend: { display: false } },
			scales: { y: { beginAtZero: true } }
		}
	});
}

// --- SHARED / UTILS ---
function showLoader(show, overlay = true) {
	const el = document.getElementById('loading-overlay');
	if (show && overlay) el.classList.remove('hidden');
	else el.classList.add('hidden');
}

function startStatusPolling() {
	// 1. Model Status (Frequency: 2s)
	setInterval(async () => {
		if (state.modelReady || state.role === 'professor') return;

		try {
			const res = await fetch('/status/');
			const data = await res.json();

			state.modelReady = data.modelo_listo;
			state.modelProgress = data.progress;

			// UI Update
			if (dom.student.statusText && state.currentView === 'student') {
				dom.student.statusText.textContent = state.modelReady
					? "Modelo Listo ✅"
					: `${data.message} (${data.progress}%)`;

				if (!state.modelReady) {
					dom.student.progressContainer.classList.remove('hidden');
					dom.student.progressBar.style.width = `${data.progress}%`;
				} else {
					dom.student.progressContainer.classList.add('hidden');
				}
			}
		} catch (e) { }
	}, 2000);

	// 2. Heartbeat (Frequency: 30s)
	setInterval(async () => {
		if (!state.user) return;

		// Validate username client-side to avoid backend 400 from invalid input
		const USER_RE = /^[A-Za-z0-9_\-\.]{1,32}$/;
		if (!USER_RE.test(state.user)) {
			console.warn('Heartbeat skipped: invalid username', state.user);
			return;
		}

		try {
			const fd = new FormData();
			fd.append('username', state.user);
			const res = await fetch('/users/heartbeat', { method: 'POST', body: fd });
			if (!res.ok) {
				console.warn('Heartbeat response', res.status, await res.text());
			} else {
				// Optional: small debug log for successful heartbeats
				// console.debug('Heartbeat OK', state.user);
			}
		} catch (e) {
			console.warn('Heartbeat failed', e);
		}
	}, 30000);
}

// --- PROFESSOR DOCUMENTS ---
async function loadStudentDocuments(username) {
	showLoader(true, false);
	try {
		const res = await fetch(`/professor/students/${username}/documents`);
		const data = await res.json();
		
		dom.prof.selectedStudentName.textContent = username;
		
		if (data.documents && data.documents.length > 0) {
			const docsHtml = data.documents.map(doc => `
				<div class="doc-item" onclick="viewDocumentDetail(${doc.id})">
					<div class="doc-item-name">${doc.filename}</div>
					<div class="doc-item-date">${new Date(doc.uploaded_at).toLocaleDateString('es-ES')} - ${doc.metricas.total_frases || 0} frases</div>
				</div>
			`).join('');
			
			dom.prof.docsList.innerHTML = docsHtml;
		} else {
			dom.prof.docsList.innerHTML = '<p class="text-muted">Este alumno no tiene documentos.</p>';
		}
		
		dom.prof.docsContainer.classList.remove('hidden');
	} catch (err) {
		console.error('Error cargando documentos:', err);
		alert('No se pudo cargar los documentos del alumno');
	} finally {
		showLoader(false);
	}
}

function closeStudentDocs() {
	dom.prof.docsContainer.classList.add('hidden');
}

async function viewDocumentDetail(docId) {
	try {
		const res = await fetch(`/documents/${docId}`);
		const data = await res.json();
		
		if (data.doc_id) {
			// Guarda el estudiante para volver después
			closeStudentDocs();
			
			// Muestra los resultados como si fuera del estudiante
			renderResults(data);
		}
	} catch (err) {
		console.error('Error cargando documento:', err);
		alert('No se pudo cargar el documento');
	}
}

// Start
init();
