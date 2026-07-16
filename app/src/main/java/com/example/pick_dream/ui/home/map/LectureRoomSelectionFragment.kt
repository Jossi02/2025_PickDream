package com.example.pick_dream.ui.home.map

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentLectureRoomSelectionBinding
import com.example.pick_dream.model.LectureRoom
import com.example.pick_dream.repository.awaitWithTimeout
import com.example.pick_dream.repository.repositoryFailure
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.launch

class LectureRoomSelectionFragment : Fragment() {
    private var _binding: FragmentLectureRoomSelectionBinding? = null
    private val binding get() = _binding!!
    private val args: LectureRoomSelectionFragmentArgs by navArgs()
    private lateinit var adapter: LectureRoomSelectionAdapter
    private val db = FirebaseFirestore.getInstance()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentLectureRoomSelectionBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setupUI()
    }

    private fun setupUI() {
        binding.tvBuildingName.text = "${args.buildingName} (${args.buildingDetail})"
        
        adapter = LectureRoomSelectionAdapter { lectureRoom ->
            val action = LectureRoomSelectionFragmentDirections
                .actionLectureRoomSelectionFragmentToManualReservationFragment(
                    roomId = lectureRoom.roomID,
                    building = args.buildingDetail,
                    roomName = lectureRoom.name
                )
            findNavController().navigate(action)
        }

        binding.rvLectureRooms.apply {
            layoutManager = LinearLayoutManager(context)
            adapter = this@LectureRoomSelectionFragment.adapter
        }

        binding.btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        loadAvailableRooms()
    }

    private fun loadAvailableRooms() {
        binding.progressBar.visibility = View.VISIBLE
        binding.tvEmptyMessage.visibility = View.GONE
        
        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val documents = db.collection("rooms")
                    .whereEqualTo("buildingName", args.buildingName)
                    .get()
                    .awaitWithTimeout()
                if (_binding == null) return@launch
                val rooms = documents.mapNotNull { doc ->
                    val rawRoom = doc.toObject(LectureRoom::class.java)
                    val roomWithDocumentId = rawRoom.copy(documentId = doc.id)
                    roomWithDocumentId.copy(
                        roomID = com.example.pick_dream.util.RoomIdUtils.canonicalRoomId(roomWithDocumentId)
                    )
                }

                val availableRooms = rooms.filter { it.isRentalAvailable }
                
                adapter.submitList(availableRooms)
                binding.progressBar.visibility = View.GONE
                
                if (availableRooms.isEmpty()) {
                    binding.tvEmptyMessage.visibility = View.VISIBLE
                    binding.tvEmptyMessage.text = "현재 사용 가능한 강의실이 없습니다."
                } else {
                    binding.tvEmptyMessage.visibility = View.GONE
                }
            } catch (e: Exception) {
                if (_binding == null) return@launch
                val message = repositoryFailure("강의실 조회", e).userMessage
                binding.progressBar.visibility = View.GONE
                binding.tvEmptyMessage.visibility = View.VISIBLE
                binding.tvEmptyMessage.text = message
                Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
