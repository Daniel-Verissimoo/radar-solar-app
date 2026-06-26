import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.8.1/firebase-app.js';
import {
    getAuth,
    sendSignInLinkToEmail,
    isSignInWithEmailLink,
    signInWithEmailLink,
} from 'https://www.gstatic.com/firebasejs/11.8.1/firebase-auth.js';

const firebaseConfig = window.radarSolarFirebaseConfig;
const storageKeys = {
    email: 'radarsolar.auth.email',
    profile: 'radarsolar.auth.profile',
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

const mapAuthError = (error) => {
    const code = error?.code || '';
    const messages = {
        'auth/quota-exceeded': 'Limite diario de envio atingido. Tente novamente mais tarde.',
        'auth/invalid-email': 'O e-mail informado nao e valido.',
        'auth/missing-email': 'Informe um e-mail para continuar.',
        'auth/unauthorized-continue-uri': 'O dominio atual nao esta autorizado para concluir o acesso.',
        'auth/network-request-failed': 'Falha de rede ao enviar o link. Verifique sua conexao e tente novamente.',
        'auth/too-many-requests': 'Muitas tentativas em pouco tempo. Aguarde alguns instantes e tente novamente.',
    };
    return messages[code] || 'Nao foi possivel concluir a autenticacao agora. Tente novamente mais tarde.';
};

window.radarSolarAuth = {
    async sendMagicLink(email, profile) {
        if (!email) {
            return { ok: false, error: 'Informe um e-mail valido.' };
        }

        const actionCodeSettings = {
            url: `${window.location.origin}/auth/confirm?profile=${profile}`,
            handleCodeInApp: true,
        };

        try {
            await sendSignInLinkToEmail(auth, email, actionCodeSettings);
            window.localStorage.setItem(storageKeys.email, email);
            window.localStorage.setItem(storageKeys.profile, profile);
            return { ok: true };
        } catch (error) {
            console.error(error);
            return { ok: false, error: mapAuthError(error), code: error?.code || '' };
        }
    },

    async completeSignIn() {
        if (!isSignInWithEmailLink(auth, window.location.href)) {
            return { status: 'idle' };
        }

        let email = window.localStorage.getItem(storageKeys.email);
        if (!email) {
            email = window.prompt('Confirme o e-mail usado para entrar no Radar Solar:');
        }
        if (!email) {
            return { status: 'error', error: 'E-mail nao informado para concluir o acesso.' };
        }

        const params = new URLSearchParams(window.location.search);
        const profile = params.get('profile') || window.localStorage.getItem(storageKeys.profile) || 'customer';
        try {
            const result = await signInWithEmailLink(auth, email, window.location.href);
            const user = result.user;
            const idToken = await user.getIdToken();
            const payload = {
                email: user.email || email,
                firebase_uid: user.uid,
                display_name: user.displayName || '',
                profile,
                idToken,
            };
            window.localStorage.removeItem(storageKeys.email);
            window.localStorage.removeItem(storageKeys.profile);
            return { status: 'success', payload };
        } catch (error) {
            console.error(error);
            return { status: 'error', error: mapAuthError(error), code: error?.code || '' };
        }
    },
};
