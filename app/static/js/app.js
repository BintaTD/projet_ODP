// Validation de l'inscription via l'API Flask
document.getElementById('register-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = 'Création...';
    
    try {
        const res = await fetch('/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: e.target['reg-username'].value,
                password: e.target['reg-password'].value
            })
        });
        const data = await res.json();
        if(res.ok) {
            alert('Compte créé avec succès ! Vous pouvez vous connecter.');
            window.location.href = '/'; // Retour à la page de connexion
        } else {
            document.getElementById('reg-error').innerText = data.message;
        }
    } catch (err) {
        document.getElementById('reg-error').innerText = 'Erreur de réseau.';
    }
    btn.innerHTML = 'Créer le compte';
});

// Validation de la connexion via l'API Flask
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = 'Connexion...';
    
    try {
        const res = await fetch('/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: e.target['login-username'].value,
                password: e.target['login-password'].value
            })
        });
        const data = await res.json();
        if(res.ok) {
            window.location.href = '/dashboard'; // Redirection vers le tableau de bord
        } else {
            document.getElementById('login-error').innerText = data.message;
            btn.innerHTML = 'Se connecter';
        }
    } catch (err) {
        document.getElementById('login-error').innerText = 'Erreur de réseau.';
        btn.innerHTML = 'Se connecter';
    }
});

// Déconnexion
document.getElementById('logout-btn')?.addEventListener('click', async () => {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/';
});

// ---------------------------------------------------------------------------
// Dashboard : liste des instances (GET /instances)
// ---------------------------------------------------------------------------

const instancesBody = document.getElementById('instances-body');

function formatDate(iso) {
    return iso ? new Date(iso).toLocaleString('fr-FR') : '—';
}

// Crée une cellule avec textContent (jamais innerHTML) pour éviter toute injection XSS
function cell(text, className) {
    const td = document.createElement('td');
    td.textContent = text;
    if (className) td.className = className;
    return td;
}

function renderInstances(instances) {
    instancesBody.replaceChildren();

    if (instances.length === 0) {
        const tr = document.createElement('tr');
        const td = cell('Aucune instance pour le moment.', 'loading-text');
        td.colSpan = 7;
        tr.appendChild(td);
        instancesBody.appendChild(tr);
        return;
    }

    for (const inst of instances) {
        const tr = document.createElement('tr');

        const nameCell = cell(inst.name);
        const distro = document.createElement('div');
        distro.className = 'cell-sub';
        distro.textContent = `${inst.distribution} · ${inst.cpu_limit} CPU · ${inst.ram_limit_mb} Mo`;
        nameCell.appendChild(distro);
        tr.appendChild(nameCell);

        const statusCell = document.createElement('td');
        const badge = document.createElement('span');
        badge.className = `status-badge status-${inst.status.toLowerCase()}`;
        badge.textContent = inst.status;
        statusCell.appendChild(badge);
        tr.appendChild(statusCell);

        tr.appendChild(cell(inst.worker));
        tr.appendChild(cell(formatDate(inst.start_time)));
        tr.appendChild(cell(formatDate(inst.end_time)));
        tr.appendChild(cell(inst.access_url || 'En attente'));

        const actionCell = document.createElement('td');
        if (inst.status === 'PENDING' || inst.status === 'RUNNING') {
            const stopBtn = document.createElement('button');
            stopBtn.className = 'btn btn-danger btn-small';
            stopBtn.textContent = 'Stop';
            stopBtn.addEventListener('click', () => stopInstance(inst.id));
            actionCell.appendChild(stopBtn);
        }
        tr.appendChild(actionCell);

        instancesBody.appendChild(tr);
    }
}

async function loadInstances() {
    try {
        const res = await fetch('/instances');
        if (res.status === 401) { window.location.href = '/'; return; }
        renderInstances(await res.json());
    } catch (err) {
        instancesBody.replaceChildren();
        const tr = document.createElement('tr');
        const td = cell('Impossible de charger les instances.', 'loading-text');
        td.colSpan = 7;
        tr.appendChild(td);
        instancesBody.appendChild(tr);
    }
}

async function stopInstance(id) {
    if (!confirm('Arrêter cette instance ?')) return;
    const res = await fetch(`/instances/${id}/stop`, { method: 'POST' });
    if (!res.ok) {
        const data = await res.json();
        alert(data.message);
    }
    loadInstances();
}

// ---------------------------------------------------------------------------
// Dashboard : formulaire de location (POST /rent)
// ---------------------------------------------------------------------------

const rentModal = document.getElementById('rent-modal');

async function openRentModal() {
    document.getElementById('rent-error').innerText = '';
    const select = document.getElementById('rent-distribution');
    const res = await fetch('/distributions');
    const distributions = await res.json();

    select.replaceChildren();
    for (const d of distributions) {
        const option = document.createElement('option');
        option.value = d.id;
        option.textContent = d.name;
        select.appendChild(option);
    }
    if (distributions.length === 0) {
        document.getElementById('rent-error').innerText = 'Aucune distribution disponible (lancez `flask seed`).';
    }
    rentModal.hidden = false;
}

document.getElementById('new-instance-btn')?.addEventListener('click', openRentModal);
document.getElementById('rent-cancel')?.addEventListener('click', () => { rentModal.hidden = true; });

document.getElementById('rent-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorBox = document.getElementById('rent-error');
    errorBox.innerText = '';

    try {
        const res = await fetch('/rent', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                distribution_id: document.getElementById('rent-distribution').value,
                cpu: document.getElementById('rent-cpu').value,
                ram_mb: document.getElementById('rent-ram').value,
                duration_minutes: document.getElementById('rent-duration').value
            })
        });
        const data = await res.json();
        if (res.ok) {
            rentModal.hidden = true;
            loadInstances();
        } else {
            errorBox.innerText = data.message;
        }
    } catch (err) {
        errorBox.innerText = 'Erreur de réseau.';
    }
});

if (instancesBody) loadInstances();
