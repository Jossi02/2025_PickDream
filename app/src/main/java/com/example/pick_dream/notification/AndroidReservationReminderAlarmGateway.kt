package com.example.pick_dream.notification

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationManagerCompat

class AndroidReservationReminderAlarmGateway(context: Context) : ReservationReminderAlarmGateway {
    private val appContext = context.applicationContext
    private val alarmManager = appContext.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    override fun schedule(record: ReservationReminderRecord) {
        if (record.reminderAtMillis <= System.currentTimeMillis()) {
            cancelPendingAlarm(record.reservationId, record.notificationId)
            appContext.sendBroadcast(reminderIntent(record.reservationId, record.notificationId))
            return
        }
        val pendingIntent = pendingIntent(
            reservationId = record.reservationId,
            notificationId = record.notificationId,
            flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        ) ?: return

        try {
            if (ReservationExactAlarmAccess.canScheduleExactAlarms(appContext)) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    alarmManager.setExactAndAllowWhileIdle(
                        AlarmManager.RTC_WAKEUP,
                        record.reminderAtMillis,
                        pendingIntent,
                    )
                } else {
                    alarmManager.setExact(
                        AlarmManager.RTC_WAKEUP,
                        record.reminderAtMillis,
                        pendingIntent,
                    )
                }
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                alarmManager.setAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    record.reminderAtMillis,
                    pendingIntent,
                )
            } else {
                alarmManager.set(AlarmManager.RTC_WAKEUP, record.reminderAtMillis, pendingIntent)
            }
        } catch (_: SecurityException) {
            alarmManager.setAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                record.reminderAtMillis,
                pendingIntent,
            )
        }
    }

    override fun cancel(reservationId: String, notificationId: Int) {
        cancelPendingAlarm(reservationId, notificationId)
        NotificationManagerCompat.from(appContext).cancel(notificationId)
    }

    private fun cancelPendingAlarm(reservationId: String, notificationId: Int) {
        pendingIntent(
            reservationId = reservationId,
            notificationId = notificationId,
            flags = PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE,
        )?.let { pendingIntent ->
            alarmManager.cancel(pendingIntent)
            pendingIntent.cancel()
        }
    }

    private fun pendingIntent(
        reservationId: String,
        notificationId: Int,
        flags: Int,
    ): PendingIntent? {
        val intent = reminderIntent(reservationId, notificationId)
        return PendingIntent.getBroadcast(appContext, notificationId, intent, flags)
    }

    private fun reminderIntent(reservationId: String, notificationId: Int) =
        Intent(appContext, ReservationAlarmReceiver::class.java).apply {
            action = ACTION_USAGE_REMINDER
            data = Uri.Builder()
                .scheme("pickdream")
                .authority("reservation-reminder")
                .appendPath(reservationId)
                .build()
            putExtra(PickDreamNotificationManager.EXTRA_RESERVATION_ID, reservationId)
            putExtra(PickDreamNotificationManager.EXTRA_NOTIFICATION_ID, notificationId)
        }

    private companion object {
        const val ACTION_USAGE_REMINDER =
            "com.example.pick_dream.notification.ACTION_USAGE_REMINDER"
    }
}
