package com.example.pick_dream.notification

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.util.ReservationTimeUtils
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** A durable reminder description. It deliberately contains no Android framework types. */
data class ReservationReminderRecord(
    val version: Int = 1,
    val reservationId: String,
    val userId: String,
    val roomId: String,
    val startTime: String,
    val endTime: String,
    val startAtMillis: Long,
    val reminderAtMillis: Long,
    val notificationId: Int,
    val title: String,
    val body: String,
    val delivered: Boolean = false,
) {
    fun sameScheduleIgnoringDelivery(other: ReservationReminderRecord): Boolean =
        version == other.version &&
            reservationId == other.reservationId &&
            userId == other.userId &&
            roomId == other.roomId &&
            startTime == other.startTime &&
            endTime == other.endTime &&
            startAtMillis == other.startAtMillis &&
            reminderAtMillis == other.reminderAtMillis &&
            notificationId == other.notificationId &&
            title == other.title &&
            body == other.body
}

/**
 * Small, versioned codec for SharedPreferences-like stores. URL encoding keeps this independent
 * of Android and makes it safe for Korean text and separator characters.
 */
object ReservationReminderRecordCodec {
    private const val VERSION = 1
    private const val SEPARATOR = '|'
    private const val FIELD_COUNT = 12

    fun encode(record: ReservationReminderRecord): String {
        val values = listOf(
            record.version.toString(),
            record.reservationId,
            record.userId,
            record.roomId,
            record.startTime,
            record.endTime,
            record.startAtMillis.toString(),
            record.reminderAtMillis.toString(),
            record.notificationId.toString(),
            record.title,
            record.body,
            record.delivered.toString(),
        )
        return values.joinToString(SEPARATOR.toString()) { encodeField(it) }
    }

    fun decode(encoded: String?): ReservationReminderRecord? {
        if (encoded.isNullOrBlank()) return null
        return try {
            val fields = encoded.split(SEPARATOR).map(::decodeField)
            if (fields.size != FIELD_COUNT || fields[0].toInt() != VERSION) return null
            ReservationReminderRecord(
                version = fields[0].toInt(),
                reservationId = fields[1],
                userId = fields[2],
                roomId = fields[3],
                startTime = fields[4],
                endTime = fields[5],
                startAtMillis = fields[6].toLong(),
                reminderAtMillis = fields[7].toLong(),
                notificationId = fields[8].toInt(),
                title = fields[9],
                body = fields[10],
                delivered = fields[11].toBooleanStrict(),
            ).takeIf { it.reservationId.isNotBlank() }
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private fun encodeField(value: String): String =
        URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    private fun decodeField(value: String): String =
        URLDecoder.decode(value, StandardCharsets.UTF_8.name())
}

interface ReservationReminderStore {
    fun loadAll(): List<ReservationReminderRecord>
    fun save(record: ReservationReminderRecord): Boolean
    fun remove(reservationId: String): Boolean
}

interface ReservationReminderAlarmGateway {
    fun schedule(record: ReservationReminderRecord)
    fun cancel(reservationId: String, notificationId: Int)
}

object ReservationReminderPlanner {
    const val REMINDER_OFFSET_MILLIS = 10 * 60 * 1000L

    private const val TITLE = "강의실 사용 시간 알림"
    private const val DELIVERY_GRACE_MILLIS = 30 * 60 * 1000L

    fun plan(reservation: Reservation, nowMillis: Long): ReservationReminderRecord? {
        val reservationId = reservation.documentId.trim()
        if (reservationId.isBlank() || reservation.status in setOf("취소", "거절")) return null

        val startTime = reservation.startTime?.trim().orEmpty()
        val endTime = reservation.endTime?.trim().orEmpty()
        val startAt = ReservationTimeUtils.parseReservationTimeMillis(startTime) ?: return null
        val endAt = ReservationTimeUtils.parseReservationTimeMillis(endTime) ?: return null
        if (startAt <= nowMillis || endAt <= startAt) return null

        val reminderAt = maxOf(startAt - REMINDER_OFFSET_MILLIS, nowMillis)
        val roomId = reservation.roomID.trim()
        val notificationId = stableNotificationId(reservationId)
        return ReservationReminderRecord(
            reservationId = reservationId,
            userId = reservation.userID,
            roomId = roomId,
            startTime = startTime,
            endTime = endTime,
            startAtMillis = startAt,
            reminderAtMillis = reminderAt,
            notificationId = notificationId,
            title = TITLE,
            body = "${roomId.ifBlank { "예약한" }} 강의실 사용 시간이 곧 시작됩니다.",
        )
    }

    fun stableNotificationId(reservationId: String): Int =
        reservationId.hashCode() and Int.MAX_VALUE

    fun isWithinDeliveryGrace(record: ReservationReminderRecord, nowMillis: Long): Boolean {
        val endAt = ReservationTimeUtils.parseReservationTimeMillis(record.endTime)
            ?: (record.startAtMillis + DELIVERY_GRACE_MILLIS)
        val latestUsefulDelivery = minOf(
            endAt,
            record.startAtMillis + DELIVERY_GRACE_MILLIS,
        )
        return nowMillis >= record.reminderAtMillis && nowMillis <= latestUsefulDelivery
    }

    fun isExpired(record: ReservationReminderRecord, nowMillis: Long): Boolean {
        val endAt = ReservationTimeUtils.parseReservationTimeMillis(record.endTime)
            ?: record.startAtMillis
        return nowMillis > endAt
    }
}

class ReservationReminderReconciler(
    private val store: ReservationReminderStore,
    private val gateway: ReservationReminderAlarmGateway,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    fun upsert(reservation: Reservation, enabled: Boolean = true): ReservationReminderRecord? {
        val reservationId = reservation.documentId.trim()
        if (!enabled) {
            if (reservationId.isNotBlank()) cancel(reservationId)
            return null
        }
        val planned = ReservationReminderPlanner.plan(reservation, clock())
        if (planned == null) {
            if (reservationId.isNotBlank()) cancel(reservationId)
            return null
        }
        return upsertPlanned(planned)
    }

    fun cancel(reservationId: String) {
        val existing = store.loadAll().filter { it.reservationId == reservationId }
        if (existing.isEmpty()) return
        if (store.remove(reservationId)) {
            existing.forEach { gateway.cancel(it.reservationId, it.notificationId) }
        }
    }

    fun reconcile(reservations: List<Reservation>, enabled: Boolean) {
        if (!enabled) {
            store.loadAll().map { it.reservationId }.distinct().forEach(::cancel)
            return
        }

        val now = clock()
        val plannedById = linkedMapOf<String, ReservationReminderRecord>()
        reservations.forEach { reservation ->
            val planned = ReservationReminderPlanner.plan(reservation, now) ?: return@forEach
            plannedById.putIfAbsent(planned.reservationId, planned)
        }

        store.loadAll()
            .map { it.reservationId }
            .distinct()
            .filterNot(plannedById::containsKey)
            .forEach(::cancel)
        plannedById.values.forEach(::upsertPlanned)
    }

    /** Re-arm records after reboot; records already past their reservation start are discarded. */
    fun restorePersisted() {
        val now = clock()
        store.loadAll().forEach { record ->
            when {
                ReservationReminderPlanner.isExpired(record, now) -> store.remove(record.reservationId)
                record.delivered -> Unit
                else -> gateway.schedule(record)
            }
        }
    }

    /** Marks a fired alarm delivered only when it is still timely enough to show. */
    fun takeForDelivery(reservationId: String, notificationId: Int): ReservationReminderRecord? {
        val record = store.loadAll().firstOrNull {
            it.reservationId == reservationId && it.notificationId == notificationId
        } ?: return null
        if (record.delivered) return null
        val now = clock()
        if (!ReservationReminderPlanner.isWithinDeliveryGrace(record, now)) {
            if (ReservationReminderPlanner.isExpired(record, now)) {
                store.remove(record.reservationId)
            }
            return null
        }

        val delivered = record.copy(delivered = true)
        return delivered.takeIf(store::save)
    }

    private fun upsertPlanned(planned: ReservationReminderRecord): ReservationReminderRecord? {
        val existing = store.loadAll().filter { it.reservationId == planned.reservationId }
        val resolved = planned.copy(
            notificationId = existing.firstOrNull()?.notificationId
                ?: allocateNotificationId(planned.notificationId, planned.reservationId),
        )
        if (existing.size == 1 && existing.single().sameScheduleIgnoringDelivery(resolved)) {
            return existing.single()
        }
        // Persist first so a process death cannot leave an untracked scheduled alarm.
        if (!store.save(resolved)) return null
        // The PendingIntent identity is stable for a reservation ID, so scheduling the changed
        // record replaces its old alarm without a cancel/remove durability gap.
        gateway.schedule(resolved)
        existing
            .filter { it.notificationId != resolved.notificationId }
            .distinctBy { it.notificationId }
            .forEach { gateway.cancel(it.reservationId, it.notificationId) }
        return resolved
    }

    private fun allocateNotificationId(preferred: Int, reservationId: String): Int {
        val usedIds = store.loadAll()
            .filterNot { it.reservationId == reservationId }
            .map { it.notificationId }
            .toHashSet()
        var candidate = preferred
        while (candidate in usedIds) {
            candidate = if (candidate == Int.MAX_VALUE) 0 else candidate + 1
        }
        return candidate
    }
}
