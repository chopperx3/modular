import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  const StatusChip({super.key, required this.label, required this.icon, required this.color});

  factory StatusChip.ok(String label)      => StatusChip(label: label, icon: Icons.check_circle, color: Colors.green);
  factory StatusChip.warn(String label)    => StatusChip(label: label, icon: Icons.warning_amber_rounded, color: Colors.orange);
  factory StatusChip.error(String label)   => StatusChip(label: label, icon: Icons.error_outline, color: Colors.red);
  factory StatusChip.neutral(String label) => StatusChip(label: label, icon: Icons.info_outline, color: Colors.blueGrey);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: .35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
