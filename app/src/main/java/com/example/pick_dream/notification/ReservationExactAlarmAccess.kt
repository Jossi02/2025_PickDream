package com.example.pick_dream.notification

import android.app.AlarmManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings

object ReservationExactAlarmAccess {
    fun canScheduleExactAlarms(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        return alarmManager.canScheduleExactAlarms()
    }

    fun requestIntent(context: Context): Intent? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || canScheduleExactAlarms(context)) {
            return null
        }
        return Intent(
            Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
            Uri.parse("package:${context.packageName}"),
        )
    }

    fun shouldShowInitialExplanation(context: Context): Boolean {
        if (requestIntent(context) == null) return false
        return !context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_INITIAL_EXPLANATION_SHOWN, false)
    }

    fun markInitialExplanationShown(context: Context) {
        context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_INITIAL_EXPLANATION_SHOWN, true)
            .apply()
    }

    private const val PREFERENCES_NAME = "reservation_reminders"
    private const val KEY_INITIAL_EXPLANATION_SHOWN = "exact_alarm_explanation_shown"
}
