package com.example.pick_dream.notification

import android.content.Context

class SharedPreferencesReservationReminderStore(context: Context) : ReservationReminderStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFERENCES_NAME,
        Context.MODE_PRIVATE,
    )

    override fun loadAll(): List<ReservationReminderRecord> =
        preferences.getStringSet(KEY_RECORDS, emptySet())
            .orEmpty()
            .toSet()
            .mapNotNull(ReservationReminderRecordCodec::decode)

    override fun save(record: ReservationReminderRecord): Boolean {
        val records = loadAll()
            .filterNot { it.reservationId == record.reservationId }
            .plus(record)
            .map(ReservationReminderRecordCodec::encode)
            .toSet()
        return preferences.edit().putStringSet(KEY_RECORDS, records).commit()
    }

    override fun remove(reservationId: String): Boolean {
        val records = loadAll()
            .filterNot { it.reservationId == reservationId }
            .map(ReservationReminderRecordCodec::encode)
            .toSet()
        return preferences.edit().putStringSet(KEY_RECORDS, records).commit()
    }

    private companion object {
        const val PREFERENCES_NAME = "reservation_reminders"
        const val KEY_RECORDS = "records_v1"
    }
}
