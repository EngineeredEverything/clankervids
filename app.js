// ClankerVids Content Studio - MVP v0.1

// Idea templates by format
const ideaTemplates = {
    "POV Commentary": [
        "POV: You're a {niche} who just realized {controversial_truth}",
        "Nobody in {niche} talks about this but {hidden_insight}",
        "POV: Explaining {topic} to someone who thinks {common_misconception}",
        "What {niche} people say vs what they actually mean",
        "The {niche} industry doesn't want you to know {secret}"
    ],
    "Satirical Explainer": [
        "How {niche} actually works (the real version)",
        "If {topic} was honest about itself",
        "The {niche} starter pack nobody shows you",
        "Things I learned after 10 years in {niche} that nobody told me",
        "{Topic} explained like you're 5 (but actually useful)"
    ],
    "Industry Insider": [
        "Red flags in {niche} that beginners always miss",
        "Why experienced {niche} people never do {common_practice}",
        "The {niche} skill that separates amateurs from pros",
        "Things that sound fake about {niche} but are actually true",
        "Why everyone in {niche} secretly hates {thing}"
    ],
    "Stitched Reaction": [
        "Reacting to the worst {niche} advice on the internet",
        "Breaking down why this {niche} take is completely wrong",
        "This is what's actually happening in {topic}",
        "Let me fix this {niche} explanation",
        "The truth about {topic} that this misses"
    ],
    "Nobody Talks About This...": [
        "Nobody talks about how {niche} is actually {reality}",
        "The dark side of {topic} nobody mentions",
        "Why {common_practice} in {niche} is dying",
        "What {niche} will look like in 5 years",
        "The {niche} problem everyone ignores"
    ]
};

// Hook strength patterns
const hookPatterns = {
    strong: [
        /^(POV|pov):/i,
        /^nobody/i,
        /^what/i,
        /^why/i,
        /^the truth/i,
        /\d+ (things|ways|secrets|mistakes)/i,
        /you('re| are) (doing|making|missing)/i,
        /don't|never|always/i
    ],
    weak: [
        /^hey guys/i,
        /^welcome/i,
        /^today/i,
        /^in this video/i,
        /^so/i
    ]
};

function generateIdea() {
    const niche = document.getElementById('ideaNiche').value.trim() || 'tech';
    const format = document.getElementById('ideaFormat').value;
    const templates = ideaTemplates[format];
    
    const ideas = templates.map(template => {
        return template
            .replace('{niche}', niche)
            .replace('{topic}', generateTopic(niche))
            .replace('{controversial_truth}', generateTruth(niche))
            .replace('{hidden_insight}', generateInsight(niche))
            .replace('{common_misconception}', generateMisconception(niche))
            .replace('{secret}', generateSecret(niche))
            .replace('{common_practice}', generatePractice(niche))
            .replace('{thing}', generateThing(niche))
            .replace('{reality}', generateReality(niche))
            .replace('{Topic}', capitalizeFirst(generateTopic(niche)));
    });
    
    const output = document.getElementById('ideaOutput');
    const list = document.getElementById('ideaList');
    
    list.innerHTML = ideas.map((idea, i) => `
        <div class="p-3 bg-gray-900 rounded border border-gray-700 hover:border-purple-500 transition-colors cursor-pointer"
             onclick="useIdea('${escapeHtml(idea)}')">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="font-medium">${idea}</div>
                </div>
                <button class="ml-2 text-purple-400 hover:text-purple-300">Use →</button>
            </div>
        </div>
    `).join('');
    
    output.classList.remove('hidden');
}

function useIdea(idea) {
    document.getElementById('scriptHook').value = idea;
    document.getElementById('scriptHook').focus();
}

function analyzeScript() {
    const hook = document.getElementById('scriptHook').value.trim();
    const body = document.getElementById('scriptBody').value.trim();
    const cta = document.getElementById('scriptCTA').value.trim();
    
    if (!hook && !body) {
        alert('Enter at least a hook or body to analyze');
        return;
    }
    
    const analysis = {
        hookStrength: analyzeHookStrength(hook),
        estimatedDuration: estimateDuration(body),
        wordCount: body.split(/\s+/).filter(w => w.length > 0).length,
        hasCTA: cta.length > 0,
        tips: []
    };
    
    // Generate tips
    if (analysis.hookStrength < 6) {
        analysis.tips.push('⚠️ Hook could be stronger - try starting with POV, numbers, or "Nobody..."');
    }
    if (analysis.estimatedDuration > 60) {
        analysis.tips.push('⚠️ Too long - aim for 20-60 seconds max');
    }
    if (analysis.estimatedDuration < 15) {
        analysis.tips.push('⚠️ Too short - might need more substance');
    }
    if (!cta) {
        analysis.tips.push('💡 Consider adding a CTA or payoff');
    }
    if (analysis.wordCount > 150) {
        analysis.tips.push('⚠️ Too wordy - tighten it up, cut filler');
    }
    
    if (analysis.tips.length === 0) {
        analysis.tips.push('✅ Script looks solid - test it!');
    }
    
    const output = document.getElementById('scriptAnalysis');
    output.innerHTML = `
        <div class="space-y-3">
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <div class="text-gray-400">Hook Strength</div>
                    <div class="text-2xl font-bold ${analysis.hookStrength >= 7 ? 'text-green-400' : analysis.hookStrength >= 5 ? 'text-yellow-400' : 'text-red-400'}">
                        ${analysis.hookStrength}/10
                    </div>
                </div>
                <div>
                    <div class="text-gray-400">Est. Duration</div>
                    <div class="text-2xl font-bold ${analysis.estimatedDuration >= 20 && analysis.estimatedDuration <= 60 ? 'text-green-400' : 'text-yellow-400'}">
                        ~${analysis.estimatedDuration}s
                    </div>
                </div>
            </div>
            <div class="text-sm">
                <div class="text-gray-400 mb-2">Analysis:</div>
                ${analysis.tips.map(tip => `<div class="mb-1">${tip}</div>`).join('')}
            </div>
            <button onclick="saveScript()" class="w-full bg-green-600 hover:bg-green-700 rounded px-4 py-2 text-sm font-semibold">
                Save Script
            </button>
        </div>
    `;
    output.classList.remove('hidden');
}

function analyzeHook() {
    const hook = document.getElementById('hookTest').value.trim();
    if (!hook) return;
    
    const score = analyzeHookStrength(hook);
    const results = document.getElementById('hookResults');
    const scoreEl = document.getElementById('hookScore');
    const feedbackEl = document.getElementById('hookFeedback');
    
    scoreEl.textContent = score + '/10';
    scoreEl.className = `text-4xl font-bold mb-2 ${score >= 7 ? 'text-green-400' : score >= 5 ? 'text-yellow-400' : 'text-red-400'}`;
    
    let feedback = '';
    if (score >= 8) {
        feedback = '🔥 Strong hook! This should stop scrollers.';
    } else if (score >= 6) {
        feedback = '✅ Decent hook. Could be punchier.';
    } else if (score >= 4) {
        feedback = '⚠️ Weak hook. Try POV, numbers, or controversy.';
    } else {
        feedback = '❌ This won\'t stop anyone. Needs complete rewrite.';
    }
    
    feedbackEl.textContent = feedback;
    results.classList.remove('hidden');
}

function analyzeHookStrength(hook) {
    if (!hook) return 0;
    
    let score = 5; // baseline
    
    // Check for strong patterns
    hookPatterns.strong.forEach(pattern => {
        if (pattern.test(hook)) score += 1;
    });
    
    // Penalize weak patterns
    hookPatterns.weak.forEach(pattern => {
        if (pattern.test(hook)) score -= 2;
    });
    
    // Length bonus (short and punchy)
    if (hook.length < 50) score += 1;
    if (hook.length > 100) score -= 1;
    
    // Question mark bonus
    if (hook.includes('?')) score += 0.5;
    
    return Math.max(0, Math.min(10, Math.round(score)));
}

function estimateDuration(text) {
    const words = text.split(/\s+/).filter(w => w.length > 0).length;
    return Math.round(words / 2.5); // ~150 words per minute = 2.5 per second
}

function saveScript() {
    const hook = document.getElementById('scriptHook').value.trim();
    const body = document.getElementById('scriptBody').value.trim();
    const cta = document.getElementById('scriptCTA').value.trim();
    
    const script = {
        hook,
        body,
        cta,
        timestamp: new Date().toISOString(),
        id: Date.now()
    };
    
    const saved = JSON.parse(localStorage.getItem('clankervids_scripts') || '[]');
    saved.unshift(script);
    localStorage.setItem('clankervids_scripts', JSON.stringify(saved));
    
    loadSavedScripts();
    alert('✅ Script saved!');
}

function loadSavedScripts() {
    const saved = JSON.parse(localStorage.getItem('clankervids_scripts') || '[]');
    const container = document.getElementById('savedScripts');
    
    if (saved.length === 0) {
        container.innerHTML = '<div class="text-gray-500 text-center py-8">No scripts saved yet. Build one above!</div>';
        return;
    }
    
    container.innerHTML = saved.map(script => `
        <div class="p-4 bg-gray-800 rounded border border-gray-700 hover:border-purple-500 transition-colors">
            <div class="flex items-start justify-between mb-2">
                <div class="font-semibold text-purple-400">${escapeHtml(script.hook)}</div>
                <button onclick="deleteScript(${script.id})" class="text-red-400 hover:text-red-300 text-sm">Delete</button>
            </div>
            ${script.body ? `<div class="text-sm text-gray-300 mb-2">${escapeHtml(script.body).substring(0, 150)}${script.body.length > 150 ? '...' : ''}</div>` : ''}
            ${script.cta ? `<div class="text-sm text-gray-400">CTA: ${escapeHtml(script.cta)}</div>` : ''}
            <div class="text-xs text-gray-500 mt-2">${new Date(script.timestamp).toLocaleString()}</div>
        </div>
    `).join('');
}

function deleteScript(id) {
    if (!confirm('Delete this script?')) return;
    const saved = JSON.parse(localStorage.getItem('clankervids_scripts') || '[]');
    const filtered = saved.filter(s => s.id !== id);
    localStorage.setItem('clankervids_scripts', JSON.stringify(filtered));
    loadSavedScripts();
}

// Helper generators
function generateTopic(niche) {
    const topics = {
        tech: ['AI', 'startup culture', 'coding', 'crypto', 'tech layoffs'],
        engineering: ['CAD software', 'safety regulations', 'project management', 'material science'],
        culture: ['gen Z behavior', 'internet trends', 'workplace dynamics', 'social media'],
        maritime: ['ship design', 'navigation tech', 'maritime law', 'cargo logistics'],
        default: ['success', 'productivity', 'career growth', 'side hustles']
    };
    const list = topics[niche.toLowerCase()] || topics.default;
    return list[Math.floor(Math.random() * list.length)];
}

function generateTruth(niche) {
    return 'it\'s not what they told you';
}

function generateInsight(niche) {
    return 'it\'s rigged from the start';
}

function generateMisconception(niche) {
    return 'hard work is enough';
}

function generateSecret(niche) {
    return 'the game is already won';
}

function generatePractice(niche) {
    return 'the thing everyone does';
}

function generateThing(niche) {
    return 'that one thing';
}

function generateReality(niche) {
    return 'broken';
}

function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Load saved scripts on page load
document.addEventListener('DOMContentLoaded', loadSavedScripts);