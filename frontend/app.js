/**
 * Duocards - Flashcard App JavaScript
 * Handles card review, swipe gestures, and API interactions
 */

// API Configuration
const API_BASE = '';

// State
let cards = [];
let currentCardIndex = 0;
let isFlipped = false;

// DOM Elements
const cardStack = document.getElementById('cardStack');
const emptyState = document.getElementById('emptyState');
const reviewButtons = document.getElementById('reviewButtons');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

// Stats elements
const statNew = document.getElementById('statNew');
const statDue = document.getElementById('statDue');
const statTotal = document.getElementById('statTotal');

// Form elements
const wordInput = document.getElementById('wordInput');
const translationInput = document.getElementById('translationInput');
const exampleInput = document.getElementById('exampleInput');

// ===== API Functions =====

async function fetchCards() {
    try {
        const response = await fetch(`${API_BASE}/api/review`);
        if (!response.ok) throw new Error('Failed to fetch cards');
        cards = await response.json();
        renderCards();
    } catch (error) {
        console.error('Error fetching cards:', error);
        showToast('Failed to load cards');
    }
}

async function fetchStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) throw new Error('Failed to fetch stats');
        const stats = await response.json();
        statNew.textContent = stats.new;
        statDue.textContent = stats.due;
        statTotal.textContent = stats.total;
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

async function submitReview(cardId, quality) {
    try {
        const response = await fetch(`${API_BASE}/api/review/${cardId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quality })
        });
        if (!response.ok) throw new Error('Failed to submit review');
        return await response.json();
    } catch (error) {
        console.error('Error submitting review:', error);
        showToast('Failed to save review');
        return null;
    }
}

async function createCard(cardData) {
    try {
        const response = await fetch(`${API_BASE}/api/cards`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cardData)
        });
        if (!response.ok) throw new Error('Failed to create card');
        return await response.json();
    } catch (error) {
        console.error('Error creating card:', error);
        showToast('Failed to save card');
        return null;
    }
}

async function generateCard(word) {
    try {
        const response = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word })
        });
        if (!response.ok) throw new Error('Failed to generate card');
        return await response.json();
    } catch (error) {
        console.error('Error generating card:', error);
        showToast('Failed to generate card');
        return null;
    }
}

async function fetchAudio(word) {
    try {
        const response = await fetch(`${API_BASE}/api/audio/${encodeURIComponent(word)}`);
        if (!response.ok) return null;
        const data = await response.json();
        return data.audio_url;
    } catch (error) {
        console.error('Error fetching audio:', error);
        return null;
    }
}

// ===== Rendering =====

function renderCards() {
    // Clear existing cards
    const existingCards = cardStack.querySelectorAll('.flashcard');
    existingCards.forEach(card => card.remove());

    if (cards.length === 0) {
        emptyState.classList.remove('hidden');
        reviewButtons.classList.add('hidden');
        return;
    }

    emptyState.classList.add('hidden');
    reviewButtons.classList.remove('hidden');

    // Render top 3 cards (stack effect)
    const visibleCards = cards.slice(currentCardIndex, currentCardIndex + 3);
    visibleCards.forEach((card, index) => {
        const cardEl = createCardElement(card, index);
        cardStack.appendChild(cardEl);
    });

    // Reset flip state
    isFlipped = false;
}

function createCardElement(card, stackIndex) {
    const cardEl = document.createElement('div');
    cardEl.className = 'flashcard';
    cardEl.dataset.id = card.id;

    // Stack positioning
    const scale = 1 - (stackIndex * 0.05);
    const translateY = stackIndex * 8;
    cardEl.style.transform = `translateY(${translateY}px) scale(${scale})`;
    cardEl.style.zIndex = 10 - stackIndex;

    cardEl.innerHTML = `
        <div class="card-inner">
            <div class="card-face card-front">
                <button class="audio-btn" onclick="playAudio('${card.word}')">🔊</button>
                <div class="card-word">${escapeHtml(card.word)}</div>
                <div class="card-hint">Tap to reveal</div>
            </div>
            <div class="card-face card-back">
                <button class="audio-btn" onclick="playAudio('${card.word}')">🔊</button>
                <div class="card-translation">${escapeHtml(card.translation)}</div>
                ${card.grammar ? `<div class="card-grammar">${escapeHtml(card.grammar)}</div>` : ''}
                ${card.example ? `<div class="card-example">${escapeHtml(card.example)}</div>` : ''}
            </div>
        </div>
    `;

    // Add event listeners only to top card
    if (stackIndex === 0) {
        setupCardInteractions(cardEl);
    }

    return cardEl;
}

function setupCardInteractions(cardEl) {
    let startX = 0;
    let startY = 0;
    let currentX = 0;
    let isDragging = false;

    // Click to flip
    cardEl.addEventListener('click', (e) => {
        if (e.target.classList.contains('audio-btn')) return;
        if (!isDragging) {
            isFlipped = !isFlipped;
            cardEl.classList.toggle('flipped', isFlipped);
        }
    });

    // Touch events for swipe
    cardEl.addEventListener('touchstart', handleStart, { passive: true });
    cardEl.addEventListener('touchmove', handleMove, { passive: false });
    cardEl.addEventListener('touchend', handleEnd);

    // Mouse events for desktop
    cardEl.addEventListener('mousedown', handleStart);
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleEnd);

    function handleStart(e) {
        isDragging = true;
        cardEl.classList.add('dragging');
        const point = e.touches ? e.touches[0] : e;
        startX = point.clientX;
        startY = point.clientY;
    }

    function handleMove(e) {
        if (!isDragging) return;
        const point = e.touches ? e.touches[0] : e;
        currentX = point.clientX - startX;

        // Apply transform
        const rotation = currentX * 0.1;
        cardEl.style.transform = `translateX(${currentX}px) rotate(${rotation}deg)`;

        // Visual feedback
        cardEl.classList.toggle('swipe-left', currentX < -50);
        cardEl.classList.toggle('swipe-right', currentX > 50);

        if (e.cancelable) e.preventDefault();
    }

    function handleEnd() {
        if (!isDragging) return;
        isDragging = false;
        cardEl.classList.remove('dragging', 'swipe-left', 'swipe-right');

        // Check if swipe threshold reached
        const threshold = 100;
        if (Math.abs(currentX) > threshold) {
            const quality = currentX > 0 ? 4 : 1; // Right = good, Left = again
            animateCardOut(cardEl, currentX > 0 ? 1 : -1);
            handleReview(quality);
        } else {
            // Reset position
            cardEl.style.transform = '';
        }

        currentX = 0;
    }
}

function animateCardOut(cardEl, direction) {
    cardEl.style.transition = 'transform 0.3s ease-out, opacity 0.3s ease-out';
    cardEl.style.transform = `translateX(${direction * 500}px) rotate(${direction * 30}deg)`;
    cardEl.style.opacity = '0';
}

// ===== Review Handling =====

async function handleReview(quality) {
    const currentCard = cards[currentCardIndex];
    if (!currentCard) return;

    // Submit to API
    await submitReview(currentCard.id, quality);

    // Move to next card
    currentCardIndex++;

    // Check if we need more cards
    if (currentCardIndex >= cards.length) {
        await fetchCards();
        currentCardIndex = 0;
    } else {
        renderCards();
    }

    // Update stats
    fetchStats();
}

// ===== Audio =====

let currentAudio = null;

async function playAudio(word) {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }

    const audioUrl = await fetchAudio(word);
    if (audioUrl) {
        currentAudio = new Audio(audioUrl);
        currentAudio.play().catch(err => {
            console.error('Audio playback failed:', err);
            showToast('Audio unavailable');
        });
    } else {
        showToast('Audio not found');
    }
}

// Make playAudio globally accessible
window.playAudio = playAudio;

// ===== Add Card View (Duocards Style) =====

const addCardView = document.getElementById('addCardView');
const examplePills = document.getElementById('examplePills');
const dictionarySection = document.getElementById('dictionarySection');
let currentGeneratedData = null;

function openAddCardView() {
    addCardView.classList.remove('hidden');
    wordInput.focus();
    // addCardView is position:fixed z-index:1000, no need to hide #app
}

function closeAddCardView() {
    addCardView.classList.add('hidden');
    clearForm();
}

function clearForm() {
    wordInput.value = '';
    translationInput.value = '';
    exampleInput.value = '';
    examplePills.innerHTML = '';
    dictionarySection.classList.add('hidden');
    currentGeneratedData = null;
}

async function handleGenerate() {
    const word = wordInput.value.trim();
    if (!word) {
        showToast('Wort eingeben');
        return;
    }

    const btn = document.getElementById('generateBtn');
    btn.classList.add('loading');
    btn.innerHTML = '<span class="spinner"></span> Laden...';

    try {
        const response = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word })
        });

        if (!response.ok) throw new Error('Generation failed');

        const data = await response.json();
        currentGeneratedData = data;

        // Fill translation
        translationInput.value = data.translation;

        // Render example pills
        renderExamplePills(data.examples);

        // Update dictionary section
        updateDictionarySection(data);

        showToast('Generiert!');
    } catch (error) {
        console.error('Generation error:', error);
        showToast('Generierung fehlgeschlagen');
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="translate-icon">⬇</span> Importieren';
    }
}

function renderExamplePills(examples) {
    examplePills.innerHTML = '';

    if (!examples || examples.length === 0) return;

    examples.forEach((example, index) => {
        const pill = document.createElement('button');
        pill.className = 'example-pill';
        pill.textContent = example;
        pill.addEventListener('click', () => selectExamplePill(pill, example));
        examplePills.appendChild(pill);
    });
}

function selectExamplePill(pill, example) {
    // Deselect all pills
    document.querySelectorAll('.example-pill').forEach(p => p.classList.remove('selected'));
    // Select clicked pill
    pill.classList.add('selected');
    // Set example input
    exampleInput.value = example;
}

function updateDictionarySection(data) {
    // Title
    document.getElementById('dictTitle').textContent = `Bedeutung von "${data.word}"`;

    // Meaning
    document.getElementById('dictMeaning').textContent = data.meaning || '';

    // Grammar
    const grammarContent = document.getElementById('grammarContent');
    grammarContent.textContent = data.grammar || '';

    // Synonyms
    const synonymsList = document.getElementById('synonymsList');
    synonymsList.innerHTML = '';
    if (data.synonyms && data.synonyms.length > 0) {
        data.synonyms.forEach(syn => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${syn.word}</strong> - ${syn.translation}`;
            synonymsList.appendChild(li);
        });
    }

    // Usage
    document.getElementById('usageContent').textContent = data.usage || '';

    // Examples with audio
    const examplesWithAudio = document.getElementById('examplesWithAudio');
    examplesWithAudio.innerHTML = '';
    if (data.examples && data.examples.length > 0) {
        data.examples.forEach(ex => {
            const div = document.createElement('div');
            div.className = 'example-item';
            div.innerHTML = `
                <span class="audio-icon" onclick="playExampleAudio('${escapeHtml(ex)}')">🔊</span>
                <span>${escapeHtml(ex)}</span>
            `;
            examplesWithAudio.appendChild(div);
        });
    }
}

async function toggleDictionarySection() {
    // If section is currently visible, just hide it
    if (!dictionarySection.classList.contains('hidden')) {
        dictionarySection.classList.add('hidden');
        return;
    }

    // If no data loaded yet, load it first
    if (!currentGeneratedData) {
        const word = wordInput.value.trim();
        if (!word) {
            showToast('Bitte erst ein Wort eingeben');
            return;
        }

        const btn = document.getElementById('grammarToggle');
        const originalContent = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Laden...';

        try {
            const response = await fetch(`${API_BASE}/api/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ word })
            });

            if (!response.ok) throw new Error('Generation failed');

            const data = await response.json();
            currentGeneratedData = data;

            // Fill translation if empty
            if (!translationInput.value.trim()) {
                translationInput.value = data.translation;
            }

            // Render example pills if not already rendered
            if (examplePills.children.length === 0) {
                renderExamplePills(data.examples);
            }

            // Update dictionary section
            updateDictionarySection(data);

            showToast('Daten geladen!');
        } catch (error) {
            console.error('Generation error:', error);
            showToast('Laden fehlgeschlagen');
            btn.disabled = false;
            btn.innerHTML = originalContent;
            return;
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    }

    // Show the section
    dictionarySection.classList.remove('hidden');
}

async function playExampleAudio(text) {
    // Use browser TTS for example sentences
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'sl-SI'; // Slovene
        speechSynthesis.speak(utterance);
    } else {
        showToast('TTS nicht verfügbar');
    }
}

window.playExampleAudio = playExampleAudio;

// TTS for word input field
function playWordTts() {
    const word = wordInput.value.trim();
    if (!word) {
        showToast('Bitte erst ein Wort eingeben');
        return;
    }
    // Use the same playAudio function as in study view
    playAudio(word);
}

// TTS for example input field
function playExampleTts() {
    const example = exampleInput.value.trim();
    if (!example) {
        showToast('Bitte erst ein Beispiel eingeben');
        return;
    }
    // Use the same playAudio function as in study view
    playAudio(example);
}

// Translation function for Slowenisch word
async function handleTranslateSlWord() {
    const word = wordInput.value.trim();
    if (!word) {
        showToast('Bitte erst ein Wort eingeben');
        return;
    }

    const btn = document.getElementById('translateSlWord');
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word })
        });

        if (!response.ok) throw new Error('Translation failed');

        const data = await response.json();
        translationInput.value = data.translation;
        showToast('Übersetzung eingefügt');
    } catch (error) {
        console.error('Translation error:', error);
        showToast('Übersetzung fehlgeschlagen');
    } finally {
        btn.disabled = false;
    }
}

// Translation function for German word -> fills everything
async function handleTranslateDeWord() {
    const germanWord = translationInput.value.trim();
    if (!germanWord) {
        showToast('Bitte erst ein deutsches Wort eingeben');
        return;
    }

    const btn = document.getElementById('translateDeWord');
    btn.disabled = true;
    btn.textContent = '...';

    try {
        const response = await fetch(`${API_BASE}/api/generate-from-german`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ german_word: germanWord })
        });

        if (!response.ok) throw new Error('Generation failed');

        const data = await response.json();
        currentGeneratedData = data;

        // Fill the Slovene word
        wordInput.value = data.word;

        // Keep German translation as entered
        // translationInput.value is already set by the user

        // Render example pills
        renderExamplePills(data.examples);

        // Update dictionary section
        updateDictionarySection(data);

        // Show dictionary section automatically
        dictionarySection.classList.remove('hidden');

        showToast('Alles eingefügt!');
    } catch (error) {
        console.error('Generation error:', error);
        showToast('Generierung fehlgeschlagen');
    } finally {
        btn.disabled = false;
        btn.textContent = '文A';
    }
}

async function handleSaveCard() {
    const word = wordInput.value.trim();
    const translation = translationInput.value.trim();

    if (!word || !translation) {
        showToast('Wort und Übersetzung erforderlich');
        return;
    }

    const cardData = {
        word,
        translation,
        grammar: currentGeneratedData?.grammar || null,
        example: exampleInput.value.trim() || null,
    };

    const created = await createCard(cardData);
    if (created) {
        showToast('Karte gespeichert!');
        // Clear form but stay in add card view
        clearForm();
        await fetchCards();
        await fetchStats();
        // Focus on word input for next card
        wordInput.focus();
    }
}

// ===== Sidebar =====

function openSidebar() {
    sidebar.classList.add('active');
    sidebarOverlay.classList.add('active');
}

function closeSidebar() {
    sidebar.classList.remove('active');
    sidebarOverlay.classList.remove('active');
}

// ===== View Navigation =====

let currentView = 'review';
let allCards = []; // All cards for browse view

function switchView(viewName) {
    currentView = viewName;

    // Update sidebar links
    document.querySelectorAll('.sidebar-link').forEach(link => {
        link.classList.toggle('active', link.dataset.view === viewName);
    });

    // Hide all views
    cardStack.classList.add('hidden');
    reviewButtons.classList.add('hidden');
    document.getElementById('browseView').classList.add('hidden');
    document.getElementById('statsView').classList.add('hidden');

    // Show selected view
    switch (viewName) {
        case 'review':
            cardStack.classList.remove('hidden');
            if (cards.length > 0) {
                reviewButtons.classList.remove('hidden');
            }
            break;
        case 'browse':
            document.getElementById('browseView').classList.remove('hidden');
            fetchAllCards();
            break;
        case 'stats':
            document.getElementById('statsView').classList.remove('hidden');
            fetchDetailedStats();
            break;
    }

    closeSidebar();
}

// ===== Browse All View =====

async function fetchAllCards() {
    try {
        const response = await fetch(`${API_BASE}/api/cards`);
        if (!response.ok) throw new Error('Failed to fetch cards');
        allCards = await response.json();
        renderCardList(allCards);
    } catch (error) {
        console.error('Error fetching all cards:', error);
        showToast('Failed to load cards');
    }
}

function renderCardList(cardsToRender) {
    const cardList = document.getElementById('cardList');

    if (cardsToRender.length === 0) {
        cardList.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <h2>No cards yet</h2>
                <p>Add some flashcards to get started</p>
            </div>
        `;
        return;
    }

    cardList.innerHTML = cardsToRender.map(card => `
        <div class="card-list-item" data-id="${card.id}" onclick="openCardDetails(${card.id})">
            <div class="card-list-content">
                <div class="card-list-word">${escapeHtml(card.word)}</div>
                <div class="card-list-translation">${escapeHtml(card.translation)}</div>
            </div>
            <div class="card-list-actions">
                <button class="card-list-btn audio" onclick="event.stopPropagation(); playAudio('${escapeHtml(card.word)}')" title="Play audio">🔊</button>
                <button class="card-list-btn delete" onclick="event.stopPropagation(); deleteCard(${card.id})" title="Delete card">🗑️</button>
            </div>
        </div>
    `).join('');
}

function filterCards(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    if (!term) {
        renderCardList(allCards);
        return;
    }

    const filtered = allCards.filter(card =>
        card.word.toLowerCase().includes(term) ||
        card.translation.toLowerCase().includes(term) ||
        (card.grammar && card.grammar.toLowerCase().includes(term)) ||
        (card.example && card.example.toLowerCase().includes(term))
    );
    renderCardList(filtered);
}

async function deleteCard(cardId) {
    if (!confirm('Delete this card?')) return;

    try {
        const response = await fetch(`${API_BASE}/api/cards/${cardId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Failed to delete card');

        showToast('Card deleted');
        // Remove from local array and re-render
        allCards = allCards.filter(c => c.id !== cardId);
        renderCardList(allCards);
        fetchStats();
    } catch (error) {
        console.error('Error deleting card:', error);
        showToast('Failed to delete card');
    }
}

// Make deleteCard globally accessible
window.deleteCard = deleteCard;

// ===== Statistics View =====

async function fetchDetailedStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) throw new Error('Failed to fetch stats');
        const stats = await response.json();

        // Update stat cards
        document.getElementById('statsTotal').textContent = stats.total;
        document.getElementById('statsNew').textContent = stats.new;
        document.getElementById('statsLearning').textContent = stats.learning;
        document.getElementById('statsMature').textContent = stats.mature;
        document.getElementById('statsDue').textContent = stats.due;

        // Update progress bar
        const masteredPercent = stats.total > 0
            ? Math.round((stats.mature / stats.total) * 100)
            : 0;
        document.getElementById('progressFill').style.width = `${masteredPercent}%`;
        document.getElementById('progressText').textContent = `${masteredPercent}% mastered`;

    } catch (error) {
        console.error('Error fetching detailed stats:', error);
    }
}

// ===== Card Details & Heatmap =====

const cardDetailsModal = document.getElementById('cardDetailsModal');

async function openCardDetails(cardId) {
    try {
        const response = await fetch(`${API_BASE}/api/cards/${cardId}/details`);
        if (!response.ok) throw new Error('Failed to fetch card details');
        const card = await response.json();

        renderCardDetails(card);
        renderHeatmap(card.history);

        cardDetailsModal.classList.remove('hidden');
    } catch (error) {
        console.error('Error opening card details:', error);
        showToast('Info konnte nicht geladen werden');
    }
}

function closeCardDetails() {
    cardDetailsModal.classList.add('hidden');
}

// Close modal when clicking outside
window.onclick = function (event) {
    if (event.target === cardDetailsModal) {
        closeCardDetails();
    }
}

function renderCardDetails(card) {
    const content = document.getElementById('modalCardContent');
    content.innerHTML = `
        <div class="detail-word">${escapeHtml(card.word)}</div>
        <div class="detail-translation">${escapeHtml(card.translation)}</div>
        
        ${card.meaning ? `
            <div class="detail-section">
                <div class="detail-label">Bedeutung</div>
                <div class="detail-text">${escapeHtml(card.meaning)}</div>
            </div>
        ` : ''}
        
        ${card.grammar ? `
            <div class="detail-section">
                <div class="detail-label">Grammatik</div>
                <div class="detail-text">${escapeHtml(card.grammar)}</div>
            </div>
        ` : ''}
        
        ${card.usage ? `
            <div class="detail-section">
                <div class="detail-label">Verwendung</div>
                <div class="detail-text">${escapeHtml(card.usage)}</div>
            </div>
        ` : ''}
        
        ${card.examples && card.examples.length > 0 ? `
            <div class="detail-section">
                <div class="detail-label">Beispiele</div>
                ${card.examples.map(ex => `<div class="detail-text">• ${escapeHtml(ex)}</div>`).join('')}
            </div>
        ` : ''}
    `;
}

function renderHeatmap(history) {
    const container = document.getElementById('heatmapContainer');
    container.innerHTML = '';

    if (!history || history.length === 0) {
        container.innerHTML = '<span style="color:var(--text-secondary); padding:10px;">Noch keine Reviews</span>';
        return;
    }

    // Sort by date just in case
    history.sort((a, b) => new Date(a.reviewed_at) - new Date(b.reviewed_at));

    history.forEach(entry => {
        const square = document.createElement('div');
        square.className = `heatmap-square level-${entry.quality}`;
        square.title = `Rating: ${entry.quality} (${new Date(entry.reviewed_at).toLocaleDateString()})`;
        container.appendChild(square);
    });
}

// Make globally accessible
window.openCardDetails = openCardDetails;
window.closeCardDetails = closeCardDetails;

// ===== Utilities =====

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message) {
    // Remove existing toast
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Remove after delay
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 2500);
}

// ===== Text Selection Translation =====

const selectionTooltip = document.getElementById('selectionTooltip');
const tooltipSelectedText = document.getElementById('tooltipSelectedText');
const tooltipLangIndicator = document.getElementById('tooltipLangIndicator');
const tooltipTranslationText = document.getElementById('tooltipTranslationText');
const tooltipError = document.getElementById('tooltipError');
const tooltipAddCard = document.getElementById('tooltipAddCard');
const tooltipClose = document.getElementById('tooltipClose');
const tooltipAudioBtn = document.getElementById('tooltipAudioBtn');

let currentSelection = null;
let currentTranslationData = null;

function getSelectedText() {
    const selection = window.getSelection();
    const text = selection.toString().trim();

    if (!text || text.length === 0) return null;

    // Don't show tooltip for selections in input fields
    const activeElement = document.activeElement;
    if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
        return null;
    }

    return {
        text: text,
        range: selection.getRangeAt(0),
        rect: selection.getRangeAt(0).getBoundingClientRect()
    };
}

function positionTooltip(rect) {
    const tooltip = selectionTooltip;
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;

    // Calculate center position
    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    let top = rect.top - tooltipRect.height - 12; // 12px gap

    // Check if tooltip goes off screen horizontally
    if (left < 16) left = 16;
    if (left + tooltipRect.width > viewportWidth - 16) {
        left = viewportWidth - tooltipRect.width - 16;
    }

    // Check if tooltip goes off screen vertically
    let arrowClass = 'arrow-bottom';
    if (top < 16) {
        // Position below selection instead
        top = rect.bottom + 12;
        arrowClass = 'arrow-top';
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;

    // Update arrow direction
    tooltip.classList.remove('arrow-top', 'arrow-bottom');
    tooltip.classList.add(arrowClass);
}

async function translateSelection(text) {
    try {
        tooltipError.style.display = 'none';
        tooltipTranslationText.innerHTML = '<span class="tooltip-spinner"></span> Übersetzen...';
        tooltipAddCard.disabled = true;
        tooltipAudioBtn.style.display = 'none';
        // Hide until translation completes

        const response = await fetch(`${API_BASE}/api/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, auto_detect: true })
        });
        if (!response.ok) throw new Error('Translation failed');

        const data = await response.json();

        // === FIX START ===
        // Check if the user's current selection still matches the text this request was for.
        // If they have selected something else in the meantime, ignore this stale response.
        if (!currentSelection || currentSelection.text !== text) {
            return;
        }
        // === FIX END ===

        currentTranslationData = data;
        // Update UI
        tooltipTranslationText.textContent = data.translation;

        const langLabel = data.detected_lang === 'sl' ?
            '🇸🇮 Slowenisch → 🇩🇪 Deutsch' : '🇩🇪 Deutsch → 🇸🇮 Slowenisch';
        tooltipLangIndicator.textContent = langLabel;
        // Always show audio button - it will play the Slovene text
        tooltipAudioBtn.style.display = 'flex';
        tooltipAddCard.disabled = false;

    } catch (error) {
        // Optional: You might also want to prevent showing errors for stale requests
        if (currentSelection && currentSelection.text !== text) return;

        console.error('Translation error:', error);
        tooltipTranslationText.textContent = '';
        tooltipError.textContent = 'Übersetzung fehlgeschlagen';
        tooltipError.style.display = 'block';
        tooltipAudioBtn.style.display = 'none';
    }
}

function showSelectionTooltip(selection) {
    currentSelection = selection;

    // Update tooltip content
    tooltipSelectedText.textContent = selection.text;
    tooltipLangIndicator.textContent = '';
    tooltipTranslationText.innerHTML = '<span class="tooltip-spinner"></span> Übersetzen...';
    tooltipError.style.display = 'none';
    tooltipAddCard.disabled = true;
    tooltipAudioBtn.style.display = 'none'; // Hide until we know language

    // Position and show tooltip
    selectionTooltip.classList.remove('show');
    setTimeout(() => {
        positionTooltip(selection.rect);
        selectionTooltip.classList.add('show');
    }, 10);

    // Translate
    translateSelection(selection.text);
}

function hideSelectionTooltip() {
    selectionTooltip.classList.remove('show');
    currentSelection = null;
    currentTranslationData = null;
}

function handleTextSelection() {
    // Small delay to ensure selection is complete
    setTimeout(() => {
        const selection = getSelectedText();

        if (selection && selection.text.length > 0) {
            showSelectionTooltip(selection);
        } else {
            hideSelectionTooltip();
        }
    }, 10);
}

function handleAddCardFromSelection() {
    if (!currentTranslationData) return;

    const isSlToGerman = currentTranslationData.detected_lang === 'sl';

    // Open add card view
    openAddCardView();

    // Pre-fill form based on detected language
    if (isSlToGerman) {
        // Slovene word selected
        wordInput.value = currentTranslationData.text;
        translationInput.value = currentTranslationData.translation;
    } else {
        // German word selected
        wordInput.value = currentTranslationData.translation;
        translationInput.value = currentTranslationData.text;
    }

    // Hide tooltip
    hideSelectionTooltip();

    // Clear text selection
    window.getSelection().removeAllRanges();

    // Focus on example input for next step
    setTimeout(() => {
        exampleInput.focus();
    }, 300);
}

// Event listeners for text selection
document.addEventListener('mouseup', handleTextSelection);
document.addEventListener('touchend', handleTextSelection);

// Prevent mouseup inside tooltip from triggering text selection handler
selectionTooltip.addEventListener('mouseup', (e) => {
    e.stopPropagation();
});

// Close tooltip
tooltipClose.addEventListener('click', (e) => {
    e.stopPropagation();
    hideSelectionTooltip();
});

// Add card from selection
tooltipAddCard.addEventListener('click', (e) => {
    e.stopPropagation();
    handleAddCardFromSelection();
});

// Play audio for selected Slovene text
tooltipAudioBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (currentTranslationData) {
        // If original text is Slovene, play it; if German, play the translation (which is Slovene)
        const sloveneText = currentTranslationData.detected_lang === 'sl'
            ? currentTranslationData.text
            : currentTranslationData.translation;
        playAudio(sloveneText);
    }
});

// Close tooltip when clicking outside
document.addEventListener('click', (e) => {
    if (selectionTooltip.classList.contains('show') &&
        !selectionTooltip.contains(e.target)) {
        hideSelectionTooltip();
    }
});

// Close tooltip on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && selectionTooltip.classList.contains('show')) {
        hideSelectionTooltip();
    }
});

// ===== Event Listeners =====

document.addEventListener('DOMContentLoaded', () => {
    // Initial data fetch
    fetchCards();
    fetchStats();

    // Add card buttons
    document.getElementById('addCardBtn').addEventListener('click', openAddCardView);
    document.getElementById('addCardBtnEmpty').addEventListener('click', openAddCardView);
    document.getElementById('closeAddCard').addEventListener('click', closeAddCardView);
    document.getElementById('saveCardBtn').addEventListener('click', handleSaveCard);
    document.getElementById('generateBtn').addEventListener('click', handleGenerate);
    document.getElementById('grammarToggle').addEventListener('click', toggleDictionarySection);

    // TTS buttons
    document.getElementById('ttsSlWord').addEventListener('click', playWordTts);
    document.getElementById('ttsExample').addEventListener('click', playExampleTts);

    // Translation buttons
    document.getElementById('translateSlWord').addEventListener('click', handleTranslateSlWord);
    document.getElementById('translateDeWord').addEventListener('click', handleTranslateDeWord);

    // Review buttons
    reviewButtons.querySelectorAll('.review-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const quality = parseInt(btn.dataset.quality);
            const topCard = cardStack.querySelector('.flashcard');
            if (topCard) {
                animateCardOut(topCard, quality > 2 ? 1 : -1);
            }
            handleReview(quality);
        });
    });

    // Menu
    document.getElementById('menuBtn').addEventListener('click', openSidebar);
    sidebarOverlay.addEventListener('click', closeSidebar);

    // Sidebar navigation
    document.querySelectorAll('.sidebar-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            switchView(link.dataset.view);
        });
    });

    // Search input
    document.getElementById('searchInput').addEventListener('input', (e) => {
        filterCards(e.target.value);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (addCardView.classList.contains('hidden') === false) return;
        if (currentView !== 'review') return;

        switch (e.key) {
            case ' ':
                e.preventDefault();
                const topCard = cardStack.querySelector('.flashcard');
                if (topCard) {
                    isFlipped = !isFlipped;
                    topCard.classList.toggle('flipped', isFlipped);
                }
                break;
            case '1':
                handleReview(1);
                break;
            case '2':
                handleReview(3);
                break;
            case '3':
                handleReview(4);
                break;
            case '4':
                handleReview(5);
                break;
        }
    });
});

// Register Service Worker for PWA
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
            .then(reg => console.log('SW registered'))
            .catch(err => console.log('SW registration failed:', err));
    });
}
