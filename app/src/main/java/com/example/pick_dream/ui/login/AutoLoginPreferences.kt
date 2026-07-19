package com.example.pick_dream.ui.login

import android.content.Context
import android.content.Intent
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.auth.FirebaseAuth

object AutoLoginDecider {
    fun shouldEnterApp(
        isEnabled: Boolean,
        hasAuthenticatedUser: Boolean,
        hasActiveSession: Boolean
    ): Boolean {
        return hasAuthenticatedUser && (isEnabled || hasActiveSession)
    }
}

object ActiveLoginSession {
    @Volatile
    private var isAuthorized = false

    fun authorize() {
        isAuthorized = true
    }

    fun clear() {
        isAuthorized = false
    }

    fun isAuthorized(): Boolean = isAuthorized
}

object AutoLoginPreferences {
    private const val PREFERENCES_NAME = "auth_preferences"
    private const val KEY_AUTO_LOGIN_ENABLED = "auto_login_enabled"

    fun isEnabled(context: Context): Boolean {
        return preferences(context).getBoolean(KEY_AUTO_LOGIN_ENABLED, false)
    }

    fun setEnabled(context: Context, isEnabled: Boolean) {
        preferences(context)
            .edit()
            .putBoolean(KEY_AUTO_LOGIN_ENABLED, isEnabled)
            .apply()
    }

    private fun preferences(context: Context) =
        context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
}

object AuthenticatedEntryGuard {
    fun redirectToLoginIfRequired(activity: AppCompatActivity): Boolean {
        val shouldEnterApp = AutoLoginDecider.shouldEnterApp(
            isEnabled = AutoLoginPreferences.isEnabled(activity),
            hasAuthenticatedUser = FirebaseAuth.getInstance().currentUser != null,
            hasActiveSession = ActiveLoginSession.isAuthorized()
        )
        if (shouldEnterApp) {
            ActiveLoginSession.authorize()
            return false
        }

        activity.startActivity(
            Intent(activity, LoginActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
        )
        activity.finish()
        return true
    }
}
