package com.example.pick_dream.model

import android.os.Parcelable
import com.google.firebase.firestore.PropertyName
import kotlinx.parcelize.Parcelize

@Parcelize
data class LectureRoom(
    val id: String = "",
    val name: String = "",
    val buildingName: String = "",
    val buildingDetail: String = "",
    val location: String = "",
    val capacity: Int = 0,
    val equipment: List<String> = emptyList(),
    var isFavorite: Boolean = false,
    val chairType: String = "",
    val isProjectorAvailable: Boolean = false,
    val isBlackboardAvailable: Boolean = false,
    @get:PropertyName("isAvailable") @set:PropertyName("isAvailable")
    var isRentalAvailable: Boolean = false,
    val imageUrl: String? = null
) : Parcelable {
    val displayBuildingName: String
        get() {
            val detail = buildingDetail.takeIf { it.isNotBlank() } ?: when (buildingName) {
                "덕문관" -> "5강의동"
                "집현관" -> "7강의동"
                "예지관" -> "4강의동"
                else -> ""
            }
            return if (detail.isNotBlank()) "$buildingName ($detail)" else buildingName
        }
}